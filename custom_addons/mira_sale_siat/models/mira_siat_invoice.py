import logging
import uuid
from decimal import Decimal

import pytz
from urllib.parse import quote_plus, urlencode

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..siat import constants, errors as siat_errors
from ..siat.amounts import fmt
from ..siat.cuf import build_cuf
from ..siat.packaging import gzip_bytes, sha256_hex
from ..siat.xml_builder import build_xml
from ..siat.xsd_validator import validate as xsd_validate

from .mira_siat_service import FISCAL_TZ

_logger = logging.getLogger(__name__)

USER = "mira_sale_siat.group_mira_siat_user"
SUPERVISOR = "mira_sale_siat.group_mira_siat_supervisor"

STATES = [
    ("draft", "Borrador"),
    ("issuing", "Emitiendo"),
    ("sent", "Enviada, en validación"),
    ("valid", "Válida"),
    ("rejected", "Rechazada"),
    ("pending_retry", "Sin respuesta del SIN"),
    ("cancellation_pending", "Anulación en curso"),
    ("cancelled", "Anulada"),
    ("reversal_pending", "Reversión en curso"),
    ("offline_issued", "Emitida fuera de línea"),
    ("packaged", "Empaquetada"),
    ("package_sent", "Paquete enviado"),
    ("package_validated", "Validada por paquete"),
]

# Estados en los que el documento tiene (o puede tener) valor fiscal.
LIVE_STATES = (
    "issuing", "sent", "valid", "pending_retry", "cancellation_pending",
    "reversal_pending", "offline_issued", "packaged", "package_sent",
    "package_validated",
)
ACCEPTED_BY_SIN = ("valid", "package_validated")


def _json_safe(value):
    if isinstance(value, Decimal):
        return fmt(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


class MiraSiatInvoice(models.Model):
    """Documento fiscal. Tiene ciclo de vida propio, separado de la venta
    (account.move): es trazable y reintentable sin tocar el dominio comercial."""
    _name = "mira.siat.invoice"
    _description = "Mira_Sale SIAT: documento fiscal"
    _order = "id desc"

    name = fields.Char(string="Documento", compute="_compute_name", store=True)
    company_id = fields.Many2one("res.company", string="Empresa", required=True,
                                 index=True, readonly=True)
    move_id = fields.Many2one("account.move", string="Venta / factura comercial",
                              required=True, index=True, readonly=True, ondelete="restrict")
    partner_id = fields.Many2one(related="move_id.partner_id", store=True, string="Cliente")
    currency_id = fields.Many2one(related="move_id.currency_id", string="Moneda")
    branch_id = fields.Many2one(related="pos_id.branch_id", store=True, string="Sucursal")
    pos_id = fields.Many2one("mira.siat.pos", string="Punto de venta", required=True,
                             readonly=True, ondelete="restrict", index=True)
    user_id = fields.Many2one("res.users", string="Emitida por", readonly=True)
    sector_code = fields.Integer(string="Documento sector", readonly=True)
    invoice_type = fields.Integer(string="Tipo de factura", readonly=True)
    emission_type = fields.Selection(
        [("1", "En línea"), ("2", "Fuera de línea")], string="Tipo de emisión",
        readonly=True)
    number = fields.Integer(string="Número de factura", readonly=True, index=True)
    cuf = fields.Char(string="CUF", readonly=True, index=True)
    cufd_id = fields.Many2one("mira.siat.cufd", string="CUFD", readonly=True,
                              ondelete="restrict")
    emission_date = fields.Datetime(string="Fecha de emisión", readonly=True)
    emission_iso = fields.Char(string="Fecha fiscal (hora Bolivia)", readonly=True)
    amount_total = fields.Monetary(string="Monto total", readonly=True)
    state = fields.Selection(STATES, string="Estado", default="draft", required=True,
                             readonly=True, index=True)
    prior_state = fields.Char(readonly=True)
    idempotency_key = fields.Char(string="Clave de idempotencia", required=True,
                                  readonly=True, index=True)
    correlation_id = fields.Char(string="Correlación", readonly=True, index=True)
    reception_code = fields.Char(string="Código de recepción", readonly=True)
    siat_status_code = fields.Integer(string="Código de estado SIN", readonly=True)
    siat_status_description = fields.Char(string="Estado SIN", readonly=True)
    siat_messages = fields.Text(string="Mensajes del SIN", readonly=True)
    error_code = fields.Char(string="Código de error", readonly=True)
    payload = fields.Json(string="Datos fiscales emitidos", readonly=True)
    xml_attachment_id = fields.Many2one("ir.attachment", string="XML", readonly=True)
    xml_sha256 = fields.Char(string="SHA-256 del XML", readonly=True)
    file_hash = fields.Char(string="Hash del archivo enviado", readonly=True)
    xsd_id = fields.Many2one("mira.siat.xsd", string="XSD usado", readonly=True)
    xsd_sha256 = fields.Char(string="Versión de XSD (SHA-256)", readonly=True)
    cancellation_reason_id = fields.Many2one(
        "mira.siat.catalog.item", string="Motivo de anulación", readonly=True)
    event_id = fields.Many2one("mira.siat.event", string="Evento de contingencia",
                               readonly=True, index=True)
    package_id = fields.Many2one("mira.siat.package", string="Paquete", readonly=True)
    number_series = fields.Char(
        string="Serie de numeración", readonly=True, default="S", required=True,
        help="«S» = numeración del sistema; en facturas manuales, el código CAFC.")
    cafc_id = fields.Many2one("mira.siat.cafc", string="Talonario CAFC", readonly=True,
                              index=True)
    retro_authorization_id = fields.Many2one(
        "mira.siat.retro.authorization", string="Autorización de fecha anterior",
        readonly=True)
    original_invoice_id = fields.Many2one(
        "mira.siat.invoice", string="Factura original", readonly=True, index=True)
    note_ids = fields.One2many(
        "mira.siat.invoice", "original_invoice_id", string="Notas de crédito-débito")
    document_kind = fields.Selection(
        [("invoice", "Factura"), ("note", "Nota de Crédito-Débito")],
        string="Tipo de documento", compute="_compute_document_kind", store=True)
    email_sent_at = fields.Datetime(string="Correo enviado el", readonly=True)
    qr_url = fields.Char(string="URL de verificación", compute="_compute_qr")
    qr_src = fields.Char(compute="_compute_qr")
    online_legend = fields.Char(compute="_compute_online_legend")

    _idempotency_uniq = models.Constraint(
        "unique(company_id, idempotency_key)",
        "Esa operación de emisión ya fue registrada (clave de idempotencia repetida).")
    _number_uniq = models.Constraint(
        "unique(pos_id, sector_code, number_series, number)",
        "Número de factura duplicado para el punto de venta.")

    @api.depends("number", "pos_id.code", "branch_id.code", "sector_code")
    def _compute_name(self):
        for inv in self:
            prefix = "NC" if inv.sector_code in constants.ADJUSTMENT_SECTORS else "F"
            inv.name = "%s-%s-%s-%s" % (prefix, inv.branch_id.code, inv.pos_id.code, inv.number)

    @api.depends("sector_code")
    def _compute_document_kind(self):
        for inv in self:
            inv.document_kind = (
                "note" if inv.sector_code in constants.ADJUSTMENT_SECTORS else "invoice")

    @api.depends("cuf", "number", "company_id")
    def _compute_qr(self):
        for inv in self:
            base = inv.company_id._mira_siat_qr_base_url()
            if not (base and inv.cuf):
                inv.qr_url = inv.qr_src = False
                continue
            inv.qr_url = "%s?%s" % (base, urlencode({
                "nit": inv.company_id.vat or "", "cuf": inv.cuf,
                "numero": inv.number, "t": 2}))
            inv.qr_src = "/report/barcode/?barcode_type=QR&value=%s&width=160&height=160" % (
                quote_plus(inv.qr_url))

    @api.depends("emission_type")
    def _compute_online_legend(self):
        for inv in self:
            if inv.emission_type == "2":
                inv.online_legend = _(
                    "Este documento es la Representación Gráfica de un Documento Fiscal "
                    "Digital emitido fuera de línea, verifique su envío con su proveedor "
                    "o en la página web www.impuestos.gob.bo")
            else:
                inv.online_legend = _(
                    "Este documento es la Representación Gráfica de un Documento Fiscal "
                    "Digital emitido en una modalidad de facturación en línea")

    def amount_in_words(self):
        """Literal del monto: «Doscientos 00/100 Bolivianos»."""
        self.ensure_one()
        amount = Decimal((self.payload or {}).get("amount_total") or "0")
        integer = int(amount)
        cents = int((amount - integer) * 100)
        try:
            from num2words import num2words
            words = num2words(integer, lang="es").capitalize()
        except Exception:
            words = str(integer)
        return "%s %02d/100 Bolivianos" % (words, cents)

    # ---- inmutabilidad ----------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        # El contexto lo envía el cliente: la bandera sola no basta, hace falta el sistema.
        if not (self.env.su and self.env.context.get("mira_siat_internal")):
            raise UserError(_("Los documentos fiscales solo se crean al emitir."))
        return super().create(vals_list)

    def write(self, vals):
        # El contexto lo envía el cliente: la bandera sola no basta, hace falta el sistema.
        if not (self.env.su and self.env.context.get("mira_siat_internal")):
            raise UserError(_(
                "Un documento fiscal no se puede modificar. Las correcciones siguen "
                "los flujos permitidos (anulación o reversión)."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Los documentos fiscales no se eliminan."))

    def _set(self, **vals):
        return self.sudo().with_context(mira_siat_internal=True).write(vals)

    # ---- acceso a archivos -----------------------------------------------
    def _xml_bytes(self):
        self.ensure_one()
        return self.sudo().xml_attachment_id.raw

    # ---- emisión ----------------------------------------------------------
    @api.model
    def _issue(self, move, idempotency_key):
        """Punto único de emisión (orquestador). Misma empresa + misma clave
        devuelve siempre el mismo documento: nunca una segunda factura."""
        service = self.env["mira.siat.service"]
        service._require_group(USER, "invoice.issue")
        move.ensure_one()
        company = move.company_id
        # Serializa emisiones concurrentes de la misma venta.
        self.env.cr.execute("SELECT id FROM account_move WHERE id = %s FOR UPDATE", [move.id])
        existing = self.sudo().search([
            ("company_id", "=", company.id), ("idempotency_key", "=", idempotency_key),
        ], limit=1)
        if existing:
            return existing
        try:
            company._mira_siat_check_active()
            invoice = self._prepare(move, idempotency_key)
        except siat_errors.SiatError as exc:
            # Nada se fijó todavía: la transacción se revierte y el número
            # reservado vuelve a estar disponible.
            raise service._user_error(exc)
        # El documento queda fijado antes de hablar con el SIN.
        service._commit()
        if invoice.state == "issuing":
            invoice._send()
        return invoice

    @api.model
    def _emission_plan(self, move, pos, sector):
        """Decide cómo se emite: en línea, en contingencia, transcripción de
        papel (CAFC) o con fecha anterior. Devuelve un dict con evento, CUFD,
        fecha fiscal, número externo y CAFC."""
        service = self.env["mira.siat.service"]
        Event = self.env["mira.siat.event"].sudo()
        now = service._fiscal_now()
        plan = {"event": Event, "when": now, "number": None, "cafc": None,
                "authorization": self.env["mira.siat.retro.authorization"]}
        is_note = sector in constants.ADJUSTMENT_SECTORS
        past_date = (move.mira_siat_manual and move.mira_siat_manual_date) \
            or move.mira_siat_backdate
        if move.mira_siat_manual or move.mira_siat_backdate:
            if is_note:
                raise UserError(_("Las notas de crédito solo se emiten en línea."))
            if not past_date:
                raise UserError(_("Indique la fecha y hora de la factura en papel."))
            if past_date > fields.Datetime.now():
                raise UserError(_("La fecha de emisión no puede ser futura."))
            event = Event.search([
                ("pos_id", "=", pos.id), ("state", "=", "open"), ("kind", "=", "past"),
                ("start_at", "<=", past_date), ("end_at", ">=", past_date)], limit=1)
            if not event:
                raise UserError(_(
                    "No hay un evento de regularización abierto para ese punto de venta "
                    "que cubra la fecha indicada. Créelo en Contingencias."))
            plan.update(event=event, when=pytz.utc.localize(past_date).astimezone(FISCAL_TZ))
            if move.mira_siat_manual:
                cafc = event.cafc_id
                if not cafc:
                    raise UserError(_(
                        "El evento no tiene talonario CAFC: no admite facturas en papel."))
                cafc._check_number(move.mira_siat_manual_number, past_date)
                plan.update(number=move.mira_siat_manual_number, cafc=cafc)
            else:
                if event.cafc_id:
                    raise UserError(_(
                        "Ese evento es de facturas en papel (CAFC). Para emitir con fecha "
                        "anterior use un evento de regularización sin talonario."))
                plan["authorization"] = self.env[
                    "mira.siat.retro.authorization"]._require(move.company_id, past_date)
            plan["cufd"] = pos._cufd_at(past_date) or event.cufd_id
            if not plan["cufd"]:
                raise siat_errors.SiatError(
                    siat_errors.CUFD, "No hay un CUFD de esa fecha para el punto de venta.")
            return plan
        event = Event.search(
            [("pos_id", "=", pos.id), ("state", "=", "open"), ("kind", "=", "live")], limit=1)
        if event:
            if is_note:
                raise UserError(_(
                    "El punto de venta está en contingencia: las notas de crédito se "
                    "emiten cuando vuelva la conexión con el SIN."))
            plan.update(event=event, cufd=event.cufd_id)
        else:
            plan["cufd"] = pos._get_cufd()
        return plan

    @api.model
    def _prepare(self, move, idempotency_key):
        service = self.env["mira.siat.service"]
        company = move.company_id
        pos = move.mira_siat_pos_id
        if not pos:
            raise UserError(_("Seleccione el punto de venta SIAT de la factura."))
        if pos.company_id != company:
            raise UserError(_("El punto de venta pertenece a otra empresa."))
        modality = int(company.mira_siat_modality)
        if modality == constants.MODALITY_ELECTRONIC:
            raise UserError(_(
                "La modalidad Electrónica en Línea requiere firma digital XMLDSig, "
                "que esta versión todavía no incluye. Use Computarizada en Línea."))
        ctx = pos._siat_context()
        contract = move._mira_siat_contract(pos)
        sector = contract["sector_code"]
        invoice_type = constants.SECTOR_INVOICE_TYPE[sector]
        plan = self._emission_plan(move, pos, sector)
        event, cufd, now, cafc = plan["event"], plan["cufd"], plan["when"], plan["cafc"]
        emission_type = constants.EMISSION_OFFLINE if event else constants.EMISSION_ONLINE
        number = plan["number"] or self.env["mira.siat.sequence"]._reserve(pos, sector)
        cuf = build_cuf(
            ctx.nit, now, ctx.branch_code, ctx.modality, emission_type, invoice_type,
            sector, number, ctx.pos_code, cufd._control_code())
        contract.update({
            "number": number,
            "cuf": cuf,
            "cufd": cufd._code(),
            "emission_iso": service._fiscal_iso(now),
        })
        if cafc:
            contract["cafc"] = cafc.name
        xml = build_xml(contract, modality)
        xsd = self.env["mira.siat.xsd"]._get(sector, modality)
        xsd_validate(xml, xsd._content())
        correlation = str(uuid.uuid4())
        invoice = self.sudo().with_context(mira_siat_internal=True).create({
            "company_id": company.id,
            "move_id": move.id,
            "pos_id": pos.id,
            "user_id": self.env.uid,
            "sector_code": sector,
            "invoice_type": invoice_type,
            "emission_type": str(emission_type),
            "number": number,
            "number_series": cafc.name if cafc else "S",
            "cuf": cuf,
            "cufd_id": cufd.id,
            "emission_date": service._to_utc_naive(now),
            "emission_iso": contract["emission_iso"],
            "amount_total": float(contract["amount_total"]),
            "state": "offline_issued" if event else "issuing",
            "idempotency_key": idempotency_key,
            "correlation_id": correlation,
            "payload": _json_safe(contract),
            "xml_sha256": sha256_hex(xml),
            "file_hash": sha256_hex(gzip_bytes(xml)),
            "xsd_id": xsd.id,
            "xsd_sha256": xsd.sha256,
            "event_id": event.id,
            "cafc_id": cafc.id if cafc else False,
            "retro_authorization_id": plan["authorization"].id,
            "original_invoice_id": contract.get("original_invoice_id") or False,
            "error_code": siat_errors.CONTINGENCY if event else False,
        })
        attachment = self.env["ir.attachment"].sudo().create({
            "name": "%s.xml" % cuf,
            "raw": xml,
            "mimetype": "application/xml",
            "res_model": self._name,
            "res_id": invoice.id,
        })
        invoice._set(xml_attachment_id=attachment.id)
        service._audit(
            "invoice.issue.offline" if event else "invoice.issue", invoice,
            after={"number": number, "cuf": cuf, "sector": sector,
                   "amount": fmt(contract["amount_total"])},
            correlation_id=correlation)
        return invoice

    def _gateway_args(self, cufd=None):
        """(gateway, ctx, cuis, cufd) para operar sobre este documento."""
        self.ensure_one()
        pos = self.pos_id
        gateway = self.company_id._mira_siat_gateway(self.correlation_id)
        cuis = pos._get_cuis()._code()
        cufd_code = (cufd or self.cufd_id)._code()
        return gateway, pos._siat_context(), cuis, cufd_code

    def _fail_comm(self, exc, state):
        """Falla de comunicación: el resultado es desconocido, no un rechazo."""
        self.pos_id._mark_comm_error()
        self._set(state=state, error_code=exc.code, siat_messages=exc.message)

    def _send(self):
        """Envía el archivo ya construido. Nunca regenera número ni CUF."""
        self.ensure_one()
        service = self.env["mira.siat.service"]
        try:
            gateway, ctx, cuis, cufd = self._gateway_args()
            result = gateway.send_invoice(
                ctx, cuis, cufd, self.sector_code, constants.EMISSION_ONLINE,
                self.invoice_type, gzip_bytes(self._xml_bytes()), self.file_hash,
                service._fiscal_iso(service._fiscal_now()))
        except siat_errors.SiatError as exc:
            self._fail_comm(exc, "pending_retry")
            return False
        self._apply_reception(result)
        return True

    def _apply_reception(self, result):
        vals = {
            "siat_status_code": result.status_code,
            "siat_status_description": result.status_description,
            "siat_messages": result.messages_text() or False,
        }
        if result.reception_code:
            vals["reception_code"] = result.reception_code
        if result.ok and result.status_code in constants.ACCEPTED_STATES:
            vals.update(state="valid", error_code=False)
        elif result.ok and result.status_code == constants.ST_PENDING:
            vals.update(state="sent", error_code=False)
        else:
            vals.update(state="rejected", error_code=siat_errors.REJECTED)
        self._set(**vals)
        if vals["state"] == "valid":
            self._auto_email("mira_sale_siat.mail_template_mira_siat_invoice")
        self.env["mira.siat.service"]._audit(
            "invoice.%s" % vals["state"], self,
            after={"status": result.status_code, "reception": result.reception_code},
            correlation_id=self.correlation_id)

    def _retry(self):
        """Tras un timeout: primero consultar, y solo reenviar el MISMO archivo
        si el SIN confirma que no lo tiene."""
        self.ensure_one()
        if self.state not in ("pending_retry", "issuing", "sent"):
            return False
        try:
            gateway, ctx, cuis, cufd = self._gateway_args()
            status = gateway.check_invoice_status(
                ctx, cuis, cufd, self.sector_code, int(self.emission_type),
                self.invoice_type, self.cuf)
        except siat_errors.SiatError as exc:
            self._fail_comm(exc, "pending_retry")
            return False
        if status.ok and status.status_code in constants.ACCEPTED_STATES:
            self._apply_reception(status)
            return True
        if status.ok and status.status_code == constants.ST_PENDING:
            self._set(state="sent", siat_status_code=status.status_code,
                      siat_status_description=status.status_description)
            return True
        if status.ok and status.status_code == constants.ST_CANCELLED:
            self._set(state="cancelled", siat_status_code=status.status_code,
                      siat_status_description=status.status_description)
            return True
        return self._send()

    # ---- anulación y reversión -------------------------------------------
    def _cancel(self, reason):
        self.ensure_one()
        service = self.env["mira.siat.service"]
        service._require_group(SUPERVISOR, "invoice.cancel")
        if self.state not in ACCEPTED_BY_SIN + ("cancellation_pending",):
            raise UserError(_("Solo se anula un documento aceptado por el SIN."))
        if self.note_ids.filtered(lambda n: n.state in LIVE_STATES):
            raise UserError(_(
                "La factura tiene notas de crédito-débito vigentes: anúlelas primero."))
        if not reason or reason.catalog_type != "motivo_anulacion" \
                or reason.company_id != self.company_id:
            raise UserError(_("Toda anulación exige un motivo del catálogo del SIN."))
        prior = self.prior_state if self.state == "cancellation_pending" else self.state
        self._set(state="cancellation_pending", prior_state=prior,
                  cancellation_reason_id=reason.id)
        service._audit("invoice.cancel.request", self, after={"reason": reason.code},
                       correlation_id=self.correlation_id)
        service._commit()
        try:
            gateway, ctx, cuis, cufd = self._gateway_args(self.pos_id._get_cufd())
            result = gateway.cancel_invoice(
                ctx, cuis, cufd, self.sector_code, int(self.emission_type),
                self.invoice_type, self.cuf, int(reason.code))
        except siat_errors.SiatError as exc:
            self._fail_comm(exc, "cancellation_pending")
            return False
        return self._apply_transition(
            result, constants.ST_CANCEL_CONFIRMED, "cancelled", prior, "invoice.cancel")

    def _revert_cancellation(self):
        self.ensure_one()
        service = self.env["mira.siat.service"]
        service._require_group(SUPERVISOR, "invoice.revert")
        if self.state not in ("cancelled", "reversal_pending"):
            raise UserError(_("Solo se revierte la anulación de un documento anulado."))
        self._set(state="reversal_pending")
        service._audit("invoice.revert.request", self, correlation_id=self.correlation_id)
        service._commit()
        try:
            gateway, ctx, cuis, cufd = self._gateway_args(self.pos_id._get_cufd())
            result = gateway.revert_cancellation(
                ctx, cuis, cufd, self.sector_code, int(self.emission_type),
                self.invoice_type, self.cuf)
        except siat_errors.SiatError as exc:
            self._fail_comm(exc, "reversal_pending")
            return False
        return self._apply_transition(
            result, constants.ST_REVERSAL_CONFIRMED, self.prior_state or "valid",
            "cancelled", "invoice.revert")

    def _apply_transition(self, result, expected_code, ok_state, ko_state, action):
        accepted = result.ok and result.status_code == expected_code
        self._set(
            state=ok_state if accepted else ko_state,
            siat_status_code=result.status_code,
            siat_status_description=result.status_description,
            siat_messages=result.messages_text() or False,
            error_code=False if accepted else siat_errors.REJECTED)
        if accepted and ok_state == "cancelled":
            self._auto_email("mira_sale_siat.mail_template_mira_siat_cancelled")
        self.env["mira.siat.service"]._audit(
            "%s.%s" % (action, "ok" if accepted else "rejected"), self,
            after={"status": result.status_code}, correlation_id=self.correlation_id)
        return accepted

    # ---- botones ----------------------------------------------------------
    def action_retry(self):
        self.env["mira.siat.service"]._require_group(USER, "invoice.retry")
        for invoice in self:
            if invoice.state == "cancellation_pending":
                invoice._cancel(invoice.cancellation_reason_id)
            elif invoice.state == "reversal_pending":
                invoice._revert_cancellation()
            else:
                invoice._retry()
        return True

    def action_cancel_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Anular ante el SIN"),
            "res_model": "mira.siat.cancel.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_invoice_id": self.id},
        }

    def action_revert_cancellation(self):
        for invoice in self:
            invoice._revert_cancellation()
        return True

    # ---- entrega al cliente ----------------------------------------------
    def _send_email(self, template_xmlid):
        """Envía el documento al correo del cliente, con PDF y XML."""
        self.ensure_one()
        partner = self.move_id.partner_id
        if not partner.email:
            raise UserError(_("El cliente no tiene correo electrónico."))
        template = self.env.ref(template_xmlid)
        template.sudo().send_mail(
            self.id, force_send=False,
            email_values={"attachment_ids": [(4, self.sudo().xml_attachment_id.id)]})
        self._set(email_sent_at=fields.Datetime.now())
        return True

    def _auto_email(self, template_xmlid):
        """Envío automático: una falla de correo nunca afecta al estado fiscal."""
        self.ensure_one()
        if not self.company_id.mira_siat_auto_email or not self.move_id.partner_id.email:
            return
        try:
            with self.env.cr.savepoint():
                self._send_email(template_xmlid)
        except Exception:
            _logger.warning("No se pudo enviar el correo del documento %s", self.name,
                            exc_info=True)

    def action_send_email(self):
        self.env["mira.siat.service"]._require_group(USER, "invoice.email")
        for invoice in self:
            invoice._send_email(
                "mira_sale_siat.mail_template_mira_siat_cancelled"
                if invoice.state == "cancelled"
                else "mira_sale_siat.mail_template_mira_siat_invoice")
        return True

    def action_print_ticket(self):
        self.ensure_one()
        return self.env.ref("mira_sale_siat.action_report_mira_siat_ticket").report_action(self)

    def action_print(self):
        self.ensure_one()
        return self.env.ref("mira_sale_siat.action_report_mira_siat_invoice").report_action(self)

    def action_view_logs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Evidencia técnica"),
            "res_model": "mira.siat.log",
            "view_mode": "list,form",
            "domain": [("correlation_id", "=", self.correlation_id)],
        }
