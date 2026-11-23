"""Avisos de trabajo al personal por WhatsApp, y lo que la persona responde.

Odoo decide y guarda el estado: a quién se avisa, qué botón apretó, qué avería se cerró.
Los botones funcionan aunque n8n no esté. Lo que la persona escribe con sus palabras se le
pasa a n8n (flujo «20 Personal»), que lo interpreta y contesta por la API.
"""
import logging

from odoo import _, api, fields, models

from odoo.addons.mirabilenet_whatsapp.whatsapp import phones
from odoo.addons.mirabilenet_whatsapp.whatsapp.gateway import WhatsAppError

from ..personal import interprete
from .mirabilenet_staff_template import ACTIONS, KINDS

_logger = logging.getLogger(__name__)

PAYLOAD_PREFIX = "mnp"
#: Cuánto se espera la nota de «No se pudo» antes de tomar el texto como un mensaje nuevo.
NOTE_WAIT_HOURS = 12
#: Un aviso que no pudo salir en este tiempo ya no sirve: se descarta en vez de mandarlo tarde.
EXPIRE_HOURS = 24


class MirabilenetStaffNotice(models.Model):
    _name = "mirabilenet.staff.notice"
    _description = "MIRABILENET: aviso al personal"
    _order = "id desc"

    user_id = fields.Many2one("res.users", string="Persona", required=True, index=True,
                              ondelete="cascade")
    kind = fields.Selection(KINDS + [("mensaje", "Mensaje de respuesta")], string="Aviso",
                            required=True, index=True)
    request_id = fields.Many2one("maintenance.request", string="Avería", index=True,
                                 ondelete="cascade")
    task_id = fields.Many2one("project.task", string="Tarea", index=True, ondelete="cascade")
    region_id = fields.Many2one(related="user_id.mirabilenet_region_id", store=True)
    destination = fields.Char(string="WhatsApp", readonly=True)
    number_id = fields.Many2one("mirabilenet.whatsapp.number", string="Número que envía",
                                readonly=True)
    parameters = fields.Json(string="Datos del aviso", readonly=True)
    text = fields.Text(string="Texto", readonly=True, help="Solo en mensajes de respuesta.")
    state = fields.Selection(
        [("pendiente", "Por enviar"), ("enviado", "Enviado"), ("fallido", "Fallido"),
         ("descartado", "Descartado")], string="Estado", default="pendiente", required=True,
        index=True, readonly=True)
    awaiting = fields.Selection([("nota", "Esperando la nota")], string="Esperando",
                                readonly=True, index=True)
    answer = fields.Char(string="Respuesta", readonly=True)
    answered_at = fields.Datetime(string="Respondió", readonly=True)
    wa_message_id = fields.Char(string="Id en Meta", readonly=True)
    sent_at = fields.Datetime(string="Enviado", readonly=True)
    attempts = fields.Integer(string="Intentos", readonly=True)
    error_detail = fields.Char(string="Error", readonly=True)

    # ------------------------------------------------------------------
    # Enviar
    # ------------------------------------------------------------------
    @api.model
    def _notify(self, users, kind, values, request=None, task=None):
        """Encola un aviso con plantilla para cada persona alcanzable. Nunca falla: si no se
        puede avisar, queda registrado por qué."""
        notices = self.browse()
        template = self.env["mirabilenet.staff.template"]._for(kind)
        for user in users.sudo():
            vals = {"user_id": user.id, "kind": kind,
                    "request_id": request.id if request else False,
                    "task_id": task.id if task else False,
                    "parameters": dict(values, persona=user.name)}
            if not user._mirabilenet_reachable():
                vals.update(state="descartado", error_detail=_("Sin WhatsApp o sin avisos."))
            elif not template:
                vals.update(state="descartado",
                            error_detail=_("No hay plantilla para este aviso."))
            else:
                vals["destination"] = user.mirabilenet_whatsapp
            notices |= self.sudo().create(vals)
        if notices.filtered(lambda n: n.state == "pendiente"):
            self.env.ref("mirabilenet_personal.cron_dispatch_staff_notices").sudo()._trigger()
        return notices

    @api.model
    def _sender_for(self, user):
        Number = self.env["mirabilenet.whatsapp.number"].sudo()
        for domain in ([("branch_id", "=", user.mirabilenet_branch_id.id)],
                       [("region_id", "=", user.mirabilenet_region_id.id)], []):
            if domain and not domain[0][2]:
                continue
            number = Number.search(domain + [("active", "=", True)], limit=1)
            if number:
                return number
        return Number

    def _payloads(self, template):
        self.ensure_one()
        return ["%s:%s:%s" % (PAYLOAD_PREFIX, self.id, action)
                for action in template._button_list()]

    @api.model
    def _cron_dispatch(self):
        pending = self.sudo().search([("state", "=", "pendiente")], order="id", limit=100)
        pending._dispatch()
        return len(pending)

    def _dispatch(self):
        Settings = self.env["mirabilenet.whatsapp.settings"]
        settings = Settings._load()
        gateway = Settings._gateway()
        expired = fields.Datetime.subtract(fields.Datetime.now(), hours=EXPIRE_HOURS)
        for notice in self.sudo().filtered(lambda n: n.state == "pendiente"):
            if notice.create_date and notice.create_date < expired:
                notice.write({"state": "descartado", "error_detail": _(
                    "Venció sin poder enviarse (%s horas).", EXPIRE_HOURS)})
                continue
            if not settings.active_messaging or not settings.configured:
                notice.error_detail = _("La mensajería está apagada o sin credenciales.")
                continue
            number = notice.number_id or self._sender_for(notice.user_id)
            if not number:
                notice.write({"state": "fallido", "error_detail": _("No hay número que envíe.")})
                continue
            attempts = notice.attempts + 1
            if notice.kind == "mensaje":
                send = lambda: gateway.send_session(  # noqa: E731
                    phone_number_id=number.phone_number_id, token=settings._secret("access_token"),
                    destino=notice.destination, tipo="texto", contenido={"texto": notice.text},
                    api_version=settings.api_version)
            else:
                template = self.env["mirabilenet.staff.template"]._for(notice.kind)
                params = notice.parameters or {}
                send = lambda template=template, params=params, notice=notice: \
                    gateway.send_template(  # noqa: E731
                        phone_number_id=number.phone_number_id,
                        token=settings._secret("access_token"), destino=notice.destination,
                        plantilla=template.meta_name, idioma=template.language,
                        parametros=[phones.clean_parameter(params.get(v))
                                    for v in template._variable_list()],
                        parameter_format="POSITIONAL", api_version=settings.api_version,
                        botones=notice._payloads(template))
            if settings.test_mode:
                notice.write({"state": "enviado", "number_id": number.id, "attempts": attempts,
                              "wa_message_id": "modo-prueba", "sent_at": fields.Datetime.now()})
                continue
            try:
                wa_id = send()
            except WhatsAppError as exc:
                exhausted = attempts >= settings.max_retries
                notice.write({"attempts": attempts, "number_id": number.id,
                              "error_detail": str(exc)[:255],
                              "state": "pendiente" if exc.reintentable and not exhausted
                              else "fallido"})
                continue
            notice.write({"state": "enviado", "number_id": number.id, "attempts": attempts,
                          "wa_message_id": wa_id, "sent_at": fields.Datetime.now(),
                          "error_detail": False})
        return True

    @api.model
    def _reply(self, user, text, request=None):
        """Contesta dentro de la conversación que la persona acaba de abrir (sin plantilla)."""
        notice = self.sudo().create({
            "user_id": user.id, "kind": "mensaje", "text": text,
            "request_id": request.id if request else False,
            "destination": user.mirabilenet_whatsapp})
        self.env.ref("mirabilenet_personal.cron_dispatch_staff_notices").sudo()._trigger()
        return notice

    # ------------------------------------------------------------------
    # Lo que responde la persona
    # ------------------------------------------------------------------
    @api.model
    def _handle_incoming(self, user, kind, text, data, external_id=""):
        """Un mensaje de alguien del personal. Devuelve lo que se hizo (para registro)."""
        user = user.sudo()
        option = (data or {}).get("opcion_id") or ""
        if kind == "respuesta" and option.startswith(PAYLOAD_PREFIX + ":"):
            try:
                _prefix, notice_id, action = option.split(":", 2)
                notice = self.sudo().browse(int(notice_id)).exists()
            except ValueError:
                notice = self.browse()
            if not notice or notice.user_id != user or action not in ACTIONS:
                self._reply(user, _("Ese botón ya no corresponde a un aviso suyo."))
                return "boton_invalido"
            return notice._apply(action)
        text = (text or "").strip()
        if not text:
            return "vacio"
        waiting = self.sudo().search([
            ("user_id", "=", user.id), ("awaiting", "=", "nota"),
            ("answered_at", ">=", fields.Datetime.subtract(fields.Datetime.now(),
                                                           hours=NOTE_WAIT_HOURS))],
            order="answered_at desc", limit=1)
        if waiting:
            waiting.awaiting = False
            return waiting._apply("no_resuelto", note=text)
        if self.env["mirabilenet.staff.inbox"]._configured():
            self.env["mirabilenet.staff.inbox"]._enqueue(user, text, external_id)
            return "a_n8n"
        return self._interpret(user, text)

    @api.model
    def _open_assignments(self, user):
        return self.env["maintenance.request"].sudo().search([
            ("user_id", "=", user.id), ("stage_id.done", "=", False),
            ("mirabilenet_service_id", "!=", False)], order="id desc")

    @api.model
    def _interpret(self, user, text):
        """Sin n8n: palabras clave sobre la última avería abierta de la persona."""
        requests = self._open_assignments(user)
        action = interprete.accion(text)
        if not requests or not action:
            self._reply(user, self._help_text(requests))
            return "ayuda"
        notice = self.sudo().search([("user_id", "=", user.id),
                                     ("request_id", "=", requests[0].id),
                                     ("kind", "=", "averia_asignada")], limit=1)
        if not notice:
            return requests[0]._mirabilenet_apply_action(action, user, note=text) or "aplicado"
        return notice._apply(action, note=text if action != "en_camino" else False)

    @api.model
    def _help_text(self, requests):
        if not requests:
            return _("No tiene averías abiertas asignadas. Cuando le asignen una, le llegará "
                     "aquí con botones para responder.")
        lines = [_("Use los botones del aviso, o escriba «arreglado», «no se pudo» o "
                   "«voy en camino». Sus averías abiertas:")]
        lines += ["- %s" % r._mirabilenet_label() for r in requests[:5]]
        return "\n".join(lines)

    def _apply(self, action, note=False):
        """Aplica la respuesta de un aviso a su avería o tarea."""
        self.ensure_one()
        self.sudo().write({"answer": ACTIONS[action], "answered_at": fields.Datetime.now()})
        if self.request_id:
            if action == "no_resuelto" and not note:
                self.sudo().awaiting = "nota"
                self._reply(self.user_id, _(
                    "Entendido. Escriba en un mensaje por qué no se pudo arreglar "
                    "(%s).", self.request_id._mirabilenet_label()), self.request_id)
                return "esperando_nota"
            return self.request_id._mirabilenet_apply_action(action, self.user_id, note=note)
        if self.task_id:
            return self.task_id._mirabilenet_apply_action(action, self.user_id)
        return "sin_destino"
