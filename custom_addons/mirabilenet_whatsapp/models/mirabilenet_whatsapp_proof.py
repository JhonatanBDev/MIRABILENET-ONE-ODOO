import base64
import logging

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

from ..whatsapp import content
from ..whatsapp.content import SendRejected
from ..whatsapp.gateway import WhatsAppError

_logger = logging.getLogger(__name__)

CASHIER = "account.group_account_invoice"


class MirabilenetWhatsappProof(models.Model):
    """Comprobante que manda el cliente. Recibirlo no aprueba nada: el pago lo registra una
    persona, y la reactivación la dispara ese pago, nunca el archivo."""
    _name = "mirabilenet.whatsapp.proof"
    _description = "MIRABILENET: comprobante de pago recibido"
    _order = "id desc"
    _rec_name = "whatsapp_message_id"

    partner_id = fields.Many2one("res.partner", string="Cliente", required=True,
                                 ondelete="restrict", index=True, readonly=True)
    region_id = fields.Many2one(related="partner_id.mirabilenet_region_id", store=True,
                                index=True, string="Región")
    charge_id = fields.Many2one(
        "account.move", string="Aviso de cobro", ondelete="restrict", index=True,
        domain="[('partner_id', '=', partner_id), ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial'))]")
    file = fields.Binary(string="Archivo", attachment=True, readonly=True)
    file_name = fields.Char(string="Nombre del archivo", readonly=True)
    mime_type = fields.Char(string="Tipo de archivo", readonly=True)
    size_bytes = fields.Integer(string="Tamaño en bytes", readonly=True)
    whatsapp_message_id = fields.Char(string="Id del mensaje entrante", required=True,
                                      readonly=True, index=True)
    state = fields.Selection(
        [("revision", "En verificación"), ("verificado", "Verificado"),
         ("rechazado", "Rechazado")], string="Estado", default="revision", required=True,
        index=True, readonly=True)
    payment_id = fields.Many2one("account.payment", string="Pago creado al verificar",
                                 ondelete="restrict", readonly=True)
    reject_reason = fields.Char(string="Motivo de rechazo", readonly=True)
    simulated = fields.Boolean(string="De prueba (simulador)", readonly=True)
    reviewed_at = fields.Datetime(string="Revisado", readonly=True)
    reviewed_by = fields.Many2one("res.users", string="Revisado por", readonly=True)
    customer_notified = fields.Boolean(string="Cliente avisado", readonly=True)

    _message_uniq = models.Constraint(
        "unique(whatsapp_message_id)", "Ese comprobante ya fue recibido.")

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise UserError(_("Los comprobantes llegan por WhatsApp, no se cargan a mano."))
        return super().create(vals_list)

    def write(self, vals):
        # Una persona solo puede cambiar a qué aviso corresponde, mientras esté en revisión.
        if not self.env.su:
            if set(vals) - {"charge_id"} or any(p.state != "revision" for p in self):
                raise UserError(_("Un comprobante se verifica o se rechaza con sus acciones."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Los comprobantes no se eliminan: son evidencia."))

    @api.model
    def _pending_charges(self, partner):
        Move = self.env["account.move"].sudo()
        return Move.search(Move._mirabilenet_open_domain() + [("partner_id", "=", partner.id)],
                           order="invoice_date_due, id")

    @api.model
    def _store(self, partner, raw, message_id, simulated=False):
        """Guarda el comprobante en verificación; si hay un solo aviso pendiente lo asocia.
        Devuelve (resultado, comprobante)."""
        Proof = self.sudo()
        previous = Proof.search([("whatsapp_message_id", "=", message_id)], limit=1)
        if previous:
            return "duplicado", previous
        mime = content.real_type(raw or b"")
        if mime is None or len(raw) > content.MAX_ATTACHMENT:
            _logger.info("Comprobante no permitido; cliente %s", partner.id)
            return "formato_no_valido", Proof
        pending = self._pending_charges(partner)
        proof = Proof.create({
            "partner_id": partner.id, "charge_id": pending.id if len(pending) == 1 else False,
            "file": base64.b64encode(raw), "mime_type": mime, "size_bytes": len(raw),
            "file_name": "comprobante%s" % content.EXTENSIONS[mime],
            "whatsapp_message_id": message_id, "simulated": simulated})
        return "guardado", proof

    @api.model
    def _store_from_meta(self, incoming, partner):
        """Descarga y guarda el adjunto de un mensaje de Meta. None si no traía archivo."""
        kind = incoming.get("type")
        if kind not in ("image", "document"):
            return None
        media_id = str((incoming.get(kind) or {}).get("id") or "")
        message_id = str(incoming.get("id") or "")[:120]
        Settings = self.env["mirabilenet.whatsapp.settings"]
        settings = Settings._load()
        if not media_id or not message_id or not settings.sudo().access_token_enc:
            return "no_recibido", self.sudo()
        previous = self.sudo().search([("whatsapp_message_id", "=", message_id)], limit=1)
        if previous:
            return "duplicado", previous
        try:
            raw, _mime = Settings._gateway().download_media(
                media_id=media_id, token=settings._secret("access_token"),
                api_version=settings.api_version)
        except WhatsAppError as exc:
            _logger.warning("No se pudo descargar el adjunto (%s)", exc.codigo or "error")
            return "no_recibido", self.sudo()
        return self._store(partner, raw, message_id)

    @api.model
    def _for_bot(self, result, proof):
        """Lo justo para que el asistente le conteste al cliente."""
        data = {"resultado": result, "comprobante_id": proof.id or None, "aviso_numero": None,
                "avisos_pendientes": 0}
        if proof:
            data["aviso_numero"] = proof.charge_id.name or None
            data["avisos_pendientes"] = len(self._pending_charges(proof.partner_id))
        return data

    def _associate(self, charge_id):
        """El cliente eligió en el chat a qué aviso corresponde. Solo mientras nadie lo
        revisó, y solo con un aviso pendiente suyo."""
        self.ensure_one()
        proof = self.sudo()
        self.env.cr.execute(
            "SELECT id FROM mirabilenet_whatsapp_proof WHERE id = %s FOR UPDATE", [proof.id])
        proof.invalidate_recordset(["state"])
        if proof.state != "revision":
            raise ValueError("El comprobante ya fue revisado.")
        try:
            charge_id = int(charge_id)
        except (TypeError, ValueError):
            charge_id = 0
        charge = self._pending_charges(proof.partner_id).filtered(lambda c: c.id == charge_id)
        if not charge:
            raise ValueError("Ese aviso no es un cobro pendiente del cliente.")
        proof.charge_id = charge
        self.env["mirabilenet.audit.log"]._log(
            "modificar", "El cliente asoció su comprobante al aviso %s por WhatsApp"
            % charge.name, record=proof, region=proof.region_id)
        return proof

    # ------------------------------------------------------------------
    # Revisión por una persona
    # ------------------------------------------------------------------
    def _notify_customer(self, text, event):
        """Le cuenta el resultado al cliente: por el chat si la ventana sigue abierta; si
        no, con la plantilla del evento."""
        self.ensure_one()
        proof = self.sudo()
        Conversation = self.env["mirabilenet.conversation"].sudo()
        conversation = Conversation.search(
            [("partner_id", "=", proof.partner_id.id), ("channel", "=", "whatsapp")], limit=1)
        if conversation and conversation._window_is_open():
            try:
                conversation._enqueue_outgoing(
                    "texto", {"texto": text}, "comprobante:%d:%s" % (proof.id, event),
                    origin="persona")
                proof.customer_notified = True
                return True
            except (SendRejected, ValueError) as exc:
                _logger.info("Aviso del comprobante %s por chat no enviado: %s", proof.id, exc)
        Message = self.env["mirabilenet.whatsapp.message"]
        try:
            message = Message._enqueue(event, charge=proof.charge_id or None,
                                       partner=proof.partner_id,
                                       extra_key="comprobante-%d" % proof.id)
        except Exception:
            _logger.exception("No se pudo encolar el aviso del comprobante %s", proof.id)
            message = Message
        if message:
            Message._trigger_dispatch()
        proof.customer_notified = bool(message)
        return bool(message)

    def action_verify(self):
        """Verificar es una decisión de una persona: registra el pago de Odoo contra la
        factura y deja anotado quién lo verificó."""
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group(CASHIER):
            raise AccessError(_("Su rol no verifica comprobantes."))
        self.check_access("read")
        proof = self.sudo()
        if proof.simulated:
            raise UserError(_(
                "Es un comprobante de prueba del simulador: no registra pagos. Rechácelo "
                "para cerrarlo."))
        if proof.state != "revision":
            raise UserError(_("El comprobante ya fue revisado."))
        charge = proof.charge_id
        if not charge:
            raise UserError(_("Asocie el comprobante a un aviso de cobro antes de verificarlo."))
        if not charge._mirabilenet_is_open():
            raise UserError(_("La factura %s ya no tiene saldo pendiente.", charge.name))
        # El pago queda a nombre de quien verifica. Si la factura queda pagada, el enganche
        # de la factura fiscal se dispara desde la conciliación.
        payment = charge.with_env(self.env)._mirabilenet_register_payment(
            memo="Comprobante %d" % proof.id)
        proof.write({"state": "verificado", "payment_id": payment.id,
                     "reviewed_at": fields.Datetime.now(), "reviewed_by": self.env.uid})
        self.env["mirabilenet.audit.log"]._log(
            "pago_registrar", "Comprobante %d verificado contra el aviso %s"
            % (proof.id, charge.name), record=proof, region=charge.mirabilenet_region_id)
        proof._notify_customer(
            "✅ Pago verificado con éxito. Registramos tu pago del aviso %s. ¡Gracias!"
            % charge.name, "comprobante_verificado")
        return True

    def action_reject(self, reason=None):
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group(CASHIER):
            raise AccessError(_("Su rol no rechaza comprobantes."))
        self.check_access("read")
        reason = (reason or self.env.context.get("mirabilenet_reason") or "").strip()
        if not reason:
            raise UserError(_("El rechazo exige un motivo escrito."))
        proof = self.sudo()
        if proof.state != "revision":
            raise UserError(_("El comprobante ya fue revisado."))
        proof.write({"state": "rechazado", "reject_reason": reason[:255],
                     "reviewed_at": fields.Datetime.now(), "reviewed_by": self.env.uid})
        if not proof.simulated:
            proof._notify_customer(
                "No pudimos validar tu comprobante: %s. Por favor envíalo de nuevo o "
                "comunícate con nosotros." % reason[:200], "comprobante_rechazado")
        return True
