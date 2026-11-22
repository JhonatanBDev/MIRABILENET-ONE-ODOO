import uuid

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from ..siat import errors as siat_errors
from ..siat.packaging import chunked

SUPERVISOR = "mira_sale_siat.group_mira_siat_supervisor"


class MiraSiatEvent(models.Model):
    """Evento significativo: abre y cierra una contingencia en un punto de venta."""
    _name = "mira.siat.event"
    _description = "Mira_Sale SIAT: evento significativo"
    _order = "id desc"

    name = fields.Char(string="Evento", compute="_compute_name", store=True)
    pos_id = fields.Many2one("mira.siat.pos", string="Punto de venta", required=True,
                             ondelete="restrict", index=True)
    company_id = fields.Many2one(related="pos_id.company_id", store=True, index=True)
    event_type_id = fields.Many2one(
        "mira.siat.catalog.item", string="Motivo del evento", required=True,
        domain="[('catalog_type', '=', 'eventos_significativos'), "
               "('company_id', '=', company_id)]")
    description = fields.Char(string="Descripción", required=True)
    kind = fields.Selection(
        [("live", "Contingencia en curso"), ("past", "Regularización (fechas pasadas)")],
        string="Tipo", default="live", required=True,
        help="En curso: el punto de venta emite fuera de línea desde ahora.\n"
             "Regularización: para transcribir facturas en papel (CAFC) o emitir con "
             "fecha anterior dentro de un periodo ya ocurrido.")
    cafc_id = fields.Many2one(
        "mira.siat.cafc", string="Talonario CAFC",
        domain="[('pos_id', '=', pos_id)]",
        help="Obligatorio para transcribir facturas emitidas en papel.")
    start_at = fields.Datetime(string="Inicio")
    end_at = fields.Datetime(string="Fin")
    cufd_id = fields.Many2one("mira.siat.cufd", string="CUFD del evento", readonly=True,
                              ondelete="restrict")
    reception_code = fields.Char(string="Código de recepción del evento", readonly=True)
    state = fields.Selection(
        [("draft", "Borrador"), ("open", "Contingencia activa"),
         ("closed", "Cerrado, sin registrar"), ("registered", "Registrado en el SIN"),
         ("done", "Conciliado")],
        string="Estado", default="draft", required=True, readonly=True, index=True)
    siat_messages = fields.Text(string="Mensajes del SIN", readonly=True)
    invoice_ids = fields.One2many("mira.siat.invoice", "event_id", string="Facturas")
    package_ids = fields.One2many("mira.siat.package", "event_id", string="Paquetes")
    invoice_count = fields.Integer(compute="_compute_invoice_count")

    @api.depends("pos_id", "start_at")
    def _compute_name(self):
        for event in self:
            event.name = "EVT-%s-%s" % (event.pos_id.code, event.id or "nuevo")

    @api.depends("invoice_ids")
    def _compute_invoice_count(self):
        for event in self:
            event.invoice_count = len(event.invoice_ids)

    @api.constrains("state", "pos_id")
    def _check_single_open(self):
        for event in self.filtered(lambda e: e.state == "open" and e.kind == "live"):
            if self.search_count([("pos_id", "=", event.pos_id.id), ("state", "=", "open"),
                                  ("kind", "=", "live")]) > 1:
                raise ValidationError(_(
                    "El punto de venta ya tiene una contingencia activa."))

    def write(self, vals):
        locked = {"start_at", "end_at", "kind", "cafc_id", "pos_id"} & set(vals)
        if locked and not (self.env.su and self.env.context.get("mira_siat_internal")) \
                and self.filtered(lambda e: e.state != "draft"):
            raise UserError(_("Los datos de un evento iniciado no se modifican."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda e: e.state != "draft"):
            raise UserError(_("Un evento iniciado no se elimina."))
        return super().unlink()

    def _service(self, action):
        service = self.env["mira.siat.service"]
        service._require_group(SUPERVISOR, action)
        return service

    def action_start(self):
        """Inicia la contingencia: desde ahora el punto emite fuera de línea."""
        service = self._service("event.start")
        for event in self:
            if event.state != "draft":
                raise UserError(_("El evento ya fue iniciado."))
            vals = {"state": "open"}
            if event.kind == "past":
                now = fields.Datetime.now()
                if not (event.start_at and event.end_at):
                    raise UserError(_("Indique el inicio y el fin del periodo a regularizar."))
                if not event.start_at < event.end_at <= now:
                    raise UserError(_(
                        "El periodo debe estar en el pasado y el fin ser posterior al inicio."))
                if event.cafc_id and event.cafc_id.pos_id != event.pos_id:
                    raise UserError(_("El talonario CAFC es de otro punto de venta."))
                cufd = event.pos_id._cufd_at(event.start_at) or event.pos_id._last_cufd()
            else:
                cufd = event.pos_id._last_cufd()
                vals.update(start_at=fields.Datetime.now(), end_at=False, cafc_id=False)
            if not cufd:
                raise UserError(_(
                    "El punto de venta nunca obtuvo un CUFD: no puede emitir fuera "
                    "de línea."))
            vals["cufd_id"] = cufd.id
            event.sudo().with_context(mira_siat_internal=True).write(vals)
            service._audit("event.start", event, after={"kind": event.kind})
        return True

    def action_close(self):
        service = self._service("event.close")
        for event in self:
            if event.state != "open":
                raise UserError(_("Solo se cierra una contingencia activa."))
            vals = {"state": "closed"}
            if event.kind == "live":
                vals["end_at"] = fields.Datetime.now()
            event.sudo().with_context(mira_siat_internal=True).write(vals)
            service._audit("event.close", event)
        return True

    def action_register(self):
        """Registra el evento ante el SIN (requiere conexión)."""
        service = self._service("event.register")
        for event in self:
            if event.state != "closed":
                raise UserError(_("Cierre la contingencia antes de registrarla."))
            pos = event.pos_id
            correlation = str(uuid.uuid4())
            try:
                event.company_id._mira_siat_check_active()
                gateway = event.company_id._mira_siat_gateway(correlation)
                result = gateway.register_event(
                    pos._siat_context(), pos._get_cuis()._code(), pos._get_cufd()._code(),
                    event.cufd_id._code(), int(event.event_type_id.code),
                    event.description, service._fiscal_iso(event.start_at),
                    service._fiscal_iso(event.end_at))
            except siat_errors.SiatError as exc:
                raise service._user_error(exc)
            if not result.ok or not result.reception_code:
                event.siat_messages = result.messages_text()
                service._audit("event.register.rejected", event,
                               correlation_id=correlation)
                service._commit()
                raise UserError(_(
                    "[%(code)s] El SIN no registró el evento:\n%(msg)s",
                    code=siat_errors.REJECTED, msg=result.messages_text()))
            event.write({"state": "registered", "reception_code": result.reception_code,
                         "siat_messages": False})
            service._audit("event.register", event,
                           after={"reception": result.reception_code},
                           correlation_id=correlation)
        return True

    def action_send_packages(self):
        """Agrupa las facturas fuera de línea en paquetes y los envía."""
        service = self._service("event.packages.send")
        Package = self.env["mira.siat.package"]
        for event in self:
            if event.state != "registered":
                raise UserError(_("Registre el evento ante el SIN antes de enviar paquetes."))
            pending = event.invoice_ids.filtered(lambda i: i.state == "offline_issued")
            size = event.company_id.mira_siat_package_size
            number = len(event.package_ids)
            for group in chunked(pending.sorted("number"), size):
                number += 1
                invoices = self.env["mira.siat.invoice"].concat(*group)
                package = Package._build(event, number, invoices)
                service._commit()
                package._send()
                service._commit()
            for package in event.package_ids.filtered(lambda p: p.state == "draft"):
                package._send()
            event._check_done()
        return True

    def action_validate_packages(self):
        service = self._service("event.packages.validate")
        for event in self:
            for package in event.package_ids.filtered(lambda p: p.state == "sent"):
                package._validate()
                service._commit()
            event._check_done()
        return True

    def _check_done(self):
        self.ensure_one()
        if self.state != "registered":
            return
        if self.invoice_ids.filtered(lambda i: i.state in ("offline_issued", "packaged",
                                                           "package_sent")):
            return
        if self.package_ids.filtered(lambda p: p.state in ("draft", "sent")):
            return
        self.state = "done"
