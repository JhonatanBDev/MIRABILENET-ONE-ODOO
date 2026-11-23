import json

from odoo import http
from odoo.http import request

from odoo.addons.mirabilenet_whatsapp.whatsapp import n8n

BASE = "/api/v1/messaging/n8n/personal"


class MirabilenetPersonalApi(http.Controller):
    """Lo que n8n (flujo «20 Personal») decide sobre un mensaje del personal. Mismo token que
    el resto de la API de n8n."""

    def _reply(self, status, body):
        return request.make_response(
            json.dumps(body, ensure_ascii=False), status=status,
            headers=[("Content-Type", "application/json; charset=utf-8")])

    @http.route(BASE + "/resultado", type="http", auth="public", methods=["POST"], csrf=False,
                save_session=False)
    def result(self, **kw):
        if not n8n.token_matches(request.httprequest.headers.get("Authorization", "")):
            return self._reply(403, {"detail": "Las credenciales de autenticación no se proveyeron."})
        try:
            data = json.loads(request.httprequest.get_data(cache=False).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            data = None
        if not isinstance(data, dict):
            return self._reply(400, {"detail": "Se esperaba un objeto JSON."})
        status, body = request.env["mirabilenet.staff.inbox"].sudo()._apply_result(data)
        return self._reply(status, body)
