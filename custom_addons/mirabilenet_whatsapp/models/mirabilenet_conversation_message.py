import base64

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..whatsapp.gateway import WhatsAppError
from .mirabilenet_whatsapp_message import STATES, STATE_ORDER

KINDS = [
    ("texto", "Texto"), ("botones", "Texto con botones"), ("lista", "Lista de opciones"),
    ("respuesta", "Botón o fila elegida"), ("ubicacion", "Ubicación"), ("imagen", "Imagen"),
    ("documento", "Documento"), ("otro", "Otro"),
]


class MirabilenetConversationMessage(models.Model):
    """Bitácora de cada mensaje de una conversación, entrante o saliente."""
    _name = "mirabilenet.conversation.message"
    _description = "MIRABILENET: mensaje de conversación"
    _order = "create_date, id"
    _rec_name = "text"

    conversation_id = fields.Many2one("mirabilenet.conversation", string="Conversación",
                                      required=True, ondelete="cascade", index=True,
                                      readonly=True)
    region_id = fields.Many2one(related="conversation_id.region_id", store=True, index=True)
    direction = fields.Selection([("entrante", "Entrante"), ("saliente", "Saliente")],
                                 string="Dirección", required=True, readonly=True)
    origin = fields.Selection(
        [("contacto", "Contacto"), ("bot", "Asistente (n8n)"), ("persona", "Persona del equipo")],
        string="Origen", required=True, readonly=True)
    kind = fields.Selection(KINDS, string="Tipo", required=True, readonly=True)
    text = fields.Text(string="Texto", readonly=True)
    data = fields.Json(string="Datos", readonly=True)
    file = fields.Binary(string="Archivo", attachment=True, readonly=True)
    external_id = fields.Char(string="Id en el canal", readonly=True, index=True)
    unique_key = fields.Char(string="Clave de deduplicación", readonly=True, index=True)
    state = fields.Selection(STATES, string="Estado", readonly=True)
    error_detail = fields.Char(string="Detalle del error", readonly=True)
    sent_at = fields.Datetime(string="Enviado", readonly=True)
    attempts = fields.Integer(string="Intentos", readonly=True)

    _external_uniq = models.Constraint("unique(external_id)", "Mensaje repetido.")
    _key_uniq = models.Constraint("unique(unique_key)", "Esa respuesta ya fue registrada.")

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise UserError(_("Los mensajes los registra el sistema."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise UserError(_("La bitácora de una conversación no se edita."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise UserError(_("La bitácora de una conversación no se elimina."))
        return super().unlink()

    @api.model
    def _trigger_dispatch(self):
        self.env.ref("mirabilenet_whatsapp.cron_dispatch_conversations").sudo()._trigger()

    @api.model
    def _cron_dispatch(self):
        pending = self.sudo().search(
            [("direction", "=", "saliente"), ("state", "=", "pendiente")], order="id", limit=200)
        pending._dispatch()
        return len(pending)

    def _dispatch(self):
        """Entrega cada respuesta por su canal y anota el resultado."""
        Settings = self.env["mirabilenet.whatsapp.settings"]
        settings = Settings._load()
        gateway = Settings._gateway()
        for message in self.sudo().filtered(lambda m: m.state == "pendiente"):
            conversation = message.conversation_id
            now = fields.Datetime.now()

            def done(external_id, message=message, conversation=conversation, now=now):
                message.write({"state": "enviado", "sent_at": now, "external_id": external_id,
                               "error_detail": False, "file": False})
                conversation.write({"last_outgoing_at": now})

            if conversation.channel == "simulador":
                done("sim-out-%d" % message.id)
                continue
            if settings.test_mode:
                done("modo-prueba-%d" % message.id)
                continue
            number = conversation.number_id
            if not number or not number.active or not settings.configured:
                message.write({"state": "fallido", "file": False, "error_detail": _(
                    "Sin número de sucursal activo o sin credenciales de Meta.")})
                continue
            body = dict(message.data or {}, texto=message.text or "")
            attempts = message.attempts + 1
            try:
                token = settings._secret("access_token")
                if message.kind in ("imagen", "documento") and not body.get("media_id"):
                    raw = base64.b64decode(message.file or b"")
                    if not raw:
                        message.write({"state": "fallido", "error_detail": _(
                            "El archivo ya no está disponible.")})
                        continue
                    body["media_id"] = gateway.upload_media(
                        phone_number_id=number.phone_number_id, token=token, contenido=raw,
                        mime=body["mime"], nombre=body["archivo_nombre"],
                        api_version=settings.api_version)
                    message.write({"data": dict(message.data or {},
                                                media_id=body["media_id"])})
                wa_id = gateway.send_session(
                    phone_number_id=number.phone_number_id, token=token,
                    destino=conversation.contact, tipo=message.kind, contenido=body,
                    api_version=settings.api_version)
            except WhatsAppError as exc:
                final = not exc.reintentable or attempts >= settings.max_retries
                vals = {"attempts": attempts, "error_detail": str(exc)[:500]}
                if final:
                    vals.update(state="fallido", file=False)
                message.write(vals)
                continue
            message.write({"attempts": attempts})
            done(wa_id)
        return True

    @api.model
    def _apply_meta_status(self, wa_id, new, status):
        message = self.sudo().search(
            [("external_id", "=", wa_id), ("direction", "=", "saliente")], limit=1)
        if not message or (STATE_ORDER[new] <= STATE_ORDER.get(message.state or "pendiente", 0)
                           and new != "fallido"):
            return False
        vals = {"state": new}
        if new == "fallido":
            error = (status.get("errors") or [{}])[0]
            vals["error_detail"] = str(error.get("title") or error.get("message") or "")[:500]
        message.write(vals)
        return True
