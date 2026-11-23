"""Lo que escribe el personal con sus palabras, para que n8n (flujo «20 Personal») lo entienda.

Viaja firmado igual que los eventos de clientes (mismo secreto), pero a su propio webhook:
el parámetro mirabilenet.n8n_staff_webhook_url. n8n contesta por
POST /api/v1/messaging/n8n/personal/resultado.
"""
from odoo import _, api, fields, models

from odoo.addons.mirabilenet_whatsapp.whatsapp import n8n

MAX_ATTEMPTS = 4
URL_PARAM = "mirabilenet.n8n_staff_webhook_url"


class MirabilenetStaffInbox(models.Model):
    _name = "mirabilenet.staff.inbox"
    _description = "MIRABILENET: mensaje del personal hacia n8n"
    _order = "id desc"

    user_id = fields.Many2one("res.users", string="Persona", required=True, ondelete="cascade")
    text = fields.Text(string="Mensaje", readonly=True)
    external_id = fields.Char(string="Id del mensaje", readonly=True, index=True)
    payload = fields.Json(string="Evento", readonly=True)
    state = fields.Selection([("pendiente", "Pendiente"), ("enviado", "Entregado"),
                              ("fallido", "Fallido"), ("atendido", "Atendido")],
                             default="pendiente", required=True, index=True, readonly=True)
    attempts = fields.Integer(readonly=True)
    error_detail = fields.Char(readonly=True)

    @api.model
    def _url(self):
        return self.env["ir.config_parameter"].sudo().get_param(URL_PARAM) or ""

    @api.model
    def _configured(self):
        return bool(self._url() and n8n.webhook_secret())

    @api.model
    def _enqueue(self, user, text, external_id=""):
        Notice = self.env["mirabilenet.staff.notice"]
        requests = Notice._open_assignments(user)
        record = self.sudo().create({"user_id": user.id, "text": text,
                                     "external_id": external_id or False})
        record.payload = {
            "evento": "mensaje_personal",
            "mensaje_id": record.id,
            "persona": {"id": user.id, "nombre": user.name, "rol": user.mirabilenet_role or "",
                        "whatsapp": user.mirabilenet_whatsapp or ""},
            "texto": text,
            "averias_abiertas": [r._mirabilenet_brief() for r in requests[:5]],
        }
        self.env.ref("mirabilenet_personal.cron_deliver_staff_inbox").sudo()._trigger()
        return record

    @api.model
    def _cron_deliver(self):
        pending = self.sudo().search([("state", "=", "pendiente")], order="id", limit=50)
        pending._deliver()
        return len(pending)

    def _deliver(self):
        Event = self.env["mirabilenet.n8n.event"]
        client, url, secret = Event._client(), self._url(), n8n.webhook_secret()
        hosts = tuple(h.strip() for h in (self.env["ir.config_parameter"].sudo().get_param(
            "mirabilenet.n8n_internal_hosts") or ",".join(n8n.DEFAULT_INTERNAL_HOSTS)
        ).split(",") if h.strip())
        Notice = self.env["mirabilenet.staff.notice"]
        for record in self.sudo().filtered(lambda r: r.state == "pendiente"):
            attempts = record.attempts + 1
            try:
                if not (url and secret):
                    raise n8n.N8NError("n8n del personal sin configurar")
                client.post(url, record.payload, secret, hosts)
            except n8n.N8NError as exc:
                final = attempts >= MAX_ATTEMPTS
                record.write({"attempts": attempts, "error_detail": str(exc)[:255],
                              "state": "fallido" if final else "pendiente"})
                if final:
                    # Que la persona no quede sin respuesta: se interpreta aquí mismo.
                    Notice._interpret(record.user_id, record.text)
                continue
            record.write({"state": "enviado", "attempts": attempts, "error_detail": False})
        return True

    @api.model
    def _apply_result(self, data):
        """Lo que decidió n8n: {mensaje_id, accion, averia_id?, nota?, respuesta?}."""
        record = self.sudo().browse(int(data.get("mensaje_id") or 0)).exists()
        if not record:
            return 404, {"detail": "Mensaje desconocido."}
        user = record.user_id
        action = data.get("accion") or ""
        note = (data.get("nota") or "").strip()[:2000] or False
        reply = (data.get("respuesta") or "").strip()[:1000]
        Request = self.env["maintenance.request"].sudo()
        request = Request.browse(int(data.get("averia_id") or 0)).exists() \
            if data.get("averia_id") else self.env["mirabilenet.staff.notice"]._open_assignments(
                user)[:1]
        if request and request.user_id != user:
            return 403, {"detail": "Esa avería no es de esta persona."}
        result = "respuesta"
        if action in ("arreglado", "no_resuelto", "en_camino"):
            if not request:
                return 409, {"detail": "La persona no tiene averías abiertas."}
            if action == "no_resuelto" and not note:
                return 400, {"detail": "Falta la nota de por qué no se pudo."}
            result = request._mirabilenet_apply_action(action, user, note=note)
        elif action == "nota" and request and note:
            request.message_post(body=_("Nota de %(u)s por WhatsApp: %(n)s", u=user.name, n=note))
            result = "nota"
        if reply:
            self.env["mirabilenet.staff.notice"]._reply(user, reply, request or None)
        record.state = "atendido"
        return 200, {"ok": True, "resultado": result}
