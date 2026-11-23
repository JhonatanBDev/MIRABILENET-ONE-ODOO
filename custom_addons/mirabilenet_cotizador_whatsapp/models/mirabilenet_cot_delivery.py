"""Envío de una cotización por WhatsApp: al trabajador que la pidió (con el botón «Enviar al
cliente») o al cliente. Odoo decide y guarda; una tarea la despacha."""
import logging

from odoo import _, api, fields, models

from odoo.addons.mirabilenet_whatsapp.whatsapp import phones
from odoo.addons.mirabilenet_whatsapp.whatsapp.gateway import WhatsAppError

_logger = logging.getLogger(__name__)

#: Prefijo del botón «Enviar al cliente»: mnc:<cotización>:enviar
PAYLOAD_PREFIX = "mnc"
PARAM_TEMPLATE = "mirabilenet_cotizador.plantilla_cotizacion"
PARAM_LANGUAGE = "mirabilenet_cotizador.plantilla_cotizacion_idioma"


class MirabilenetCotDelivery(models.Model):
    _name = "mirabilenet.cot.delivery"
    _description = "Cotizador: envío por WhatsApp"
    _order = "id desc"
    _rec_name = "order_id"

    order_id = fields.Many2one("sale.order", string="Cotización", required=True, index=True,
                               ondelete="cascade")
    target = fields.Selection([("trabajador", "Al trabajador"), ("cliente", "Al cliente")],
                              string="Para", required=True)
    user_id = fields.Many2one("res.users", string="Trabajador",
                              help="Quién la pidió, o quién la envía al cliente.")
    destination = fields.Char(string="WhatsApp", required=True, readonly=True)
    with_button = fields.Boolean(string="Con botón «Enviar al cliente»", readonly=True)
    state = fields.Selection([("pendiente", "Por enviar"), ("enviado", "Enviado"),
                              ("fallido", "Fallido")], string="Estado", default="pendiente",
                             required=True, index=True, readonly=True)
    channel = fields.Char(string="Cómo salió", readonly=True,
                          help="Dentro de la conversación abierta, o con plantilla.")
    wa_message_id = fields.Char(string="Id en Meta", readonly=True)
    sent_at = fields.Datetime(string="Enviado", readonly=True)
    attempts = fields.Integer(string="Intentos", readonly=True)
    error_detail = fields.Char(string="Error", readonly=True)

    # ------------------------------------------------------------------
    @api.model
    def _queue(self, order, target, destination, user=None, with_button=False):
        """Deja el envío en cola. Devuelve el envío, o uno vacío y el motivo."""
        try:
            number = phones.normalize_number(destination)
        except phones.NotSendable as exc:
            return self.browse(), str(exc)
        delivery = self.sudo().create({
            "order_id": order.id, "target": target, "destination": number,
            "user_id": user.id if user else False, "with_button": with_button})
        self.env.ref("mirabilenet_cotizador_whatsapp.cron_dispatch_cot_deliveries").sudo(
        )._trigger()
        return delivery, False

    @api.model
    def _cron_dispatch(self):
        pending = self.sudo().search([("state", "=", "pendiente")], order="id", limit=50)
        pending._dispatch()
        return len(pending)

    def _sender(self):
        """El número de la sucursal que envía: el de la conversación abierta con el cliente,
        o el del trabajador."""
        self.ensure_one()
        conversation = self._open_conversation()
        if conversation.number_id:
            return conversation.number_id
        user = self.user_id or self.order_id.mirabilenet_cot_requester_id or self.env.user
        return self.env["mirabilenet.staff.notice"]._sender_for(user)

    def _open_conversation(self):
        """Conversación de WhatsApp con ese número y con la ventana de 24 horas abierta."""
        self.ensure_one()
        conversations = self.env["mirabilenet.conversation"].sudo().search(
            [("channel", "=", "whatsapp"), ("contact", "=", self.destination)],
            order="last_incoming_at desc", limit=3)
        return conversations.filtered(lambda c: c._window_is_open())[:1]

    def _dispatch(self):
        Settings = self.env["mirabilenet.whatsapp.settings"]
        settings = Settings._load()
        gateway = Settings._gateway()
        Param = self.env["ir.config_parameter"].sudo()
        for delivery in self.sudo().filtered(lambda d: d.state == "pendiente"):
            order = delivery.order_id
            now = fields.Datetime.now()
            if not settings.active_messaging or not settings.configured:
                delivery.error_detail = _("La mensajería está apagada o sin credenciales.")
                continue
            if settings.test_mode:
                delivery._done("modo-prueba", "modo de prueba", now)
                continue
            number = delivery._sender()
            if not number:
                delivery.write({"state": "fallido",
                                "error_detail": _("No hay número que envíe.")})
                continue
            attempts = delivery.attempts + 1
            summary = order._mirabilenet_cot_whatsapp_summary()[:1000]
            try:
                token = settings._secret("access_token")
                pdf, name = order._mirabilenet_cot_pdf()
                media_id = gateway.upload_media(
                    phone_number_id=number.phone_number_id, token=token, contenido=pdf,
                    mime="application/pdf", nombre=name, api_version=settings.api_version)
                in_window = delivery.target == "trabajador" or delivery._open_conversation()
                if in_window:
                    wa_id = gateway.send_session(
                        phone_number_id=number.phone_number_id, token=token,
                        destino=delivery.destination, tipo="documento",
                        contenido={"media_id": media_id, "archivo_nombre": name,
                                   "texto": summary}, api_version=settings.api_version)
                    channel = "conversación abierta"
                else:
                    # Fuera de la ventana de 24 h solo se puede escribir con una plantilla.
                    wa_id = gateway.send_template(
                        phone_number_id=number.phone_number_id, token=token,
                        destino=delivery.destination,
                        plantilla=Param.get_param(PARAM_TEMPLATE, "cotizacion"),
                        idioma=Param.get_param(PARAM_LANGUAGE, "es"),
                        parametros=[phones.clean_parameter(order.partner_id.name),
                                    phones.clean_parameter(order.name),
                                    phones.clean_parameter("%s %s" % (
                                        order.currency_id.name or "Bs",
                                        order.mirabilenet_cot_fmt(order.mirabilenet_cot_total)))],
                        parameter_format="POSITIONAL", api_version=settings.api_version,
                        header_document={"id": media_id, "filename": name})
                    channel = "plantilla"
                if delivery.with_button:
                    gateway.send_session(
                        phone_number_id=number.phone_number_id, token=token,
                        destino=delivery.destination, tipo="botones",
                        contenido={"texto": _("¿Se la envío al cliente %s?",
                                              order.partner_id.name)[:1000],
                                   "botones": [{"id": "%s:%d:enviar" % (PAYLOAD_PREFIX, order.id),
                                                "titulo": _("Enviar al cliente")}]},
                        api_version=settings.api_version)
            except WhatsAppError as exc:
                final = not exc.reintentable or attempts >= settings.max_retries
                delivery.write({"attempts": attempts, "error_detail": str(exc)[:255],
                                "state": "fallido" if final else "pendiente"})
                if final:
                    order.message_post(body=_("No se pudo enviar por WhatsApp: %s", exc))
                continue
            delivery.attempts = attempts
            delivery._done(wa_id, channel, now)
        return True

    def _done(self, wa_id, channel, now):
        self.ensure_one()
        self.write({"state": "enviado", "wa_message_id": wa_id, "channel": channel,
                    "sent_at": now, "error_detail": False})
        order = self.order_id
        if self.target == "cliente":
            if order.mirabilenet_cot_stage == "aprobada":
                order.action_mirabilenet_cot_mark_sent()
            order.message_post(body=_("Cotización enviada al cliente por WhatsApp (%s).",
                                      self.destination))
        else:
            order.message_post(body=_("Cotización enviada a %s por WhatsApp.",
                                      self.user_id.name or self.destination))
