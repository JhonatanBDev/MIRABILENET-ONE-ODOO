import json

from odoo import http
from odoo.http import request

from ..models.mirabilenet_router import ENROLL_PATH

MAX_BODY = 8192


class MirabilenetEnrollment(http.Controller):

    @http.route(ENROLL_PATH, type="http", auth="public", methods=["POST"], csrf=False,
                save_session=False)
    def complete_enrollment(self, **_kwargs):
        """Lo invoca el router al final del guion. Único punto público del módulo de red:
        se autentica con el código de un solo uso."""
        raw = request.httprequest.get_data(cache=False)[:MAX_BODY]
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            payload = None
        if not isinstance(payload, dict):
            status, body = 400, {"detail": "Se esperaba un objeto JSON."}
        else:
            status, body = request.env["mirabilenet.enrollment.token"].sudo()._complete(
                payload, ip=request.httprequest.remote_addr)
        return request.make_response(
            json.dumps(body), status=status, headers=[("Content-Type", "application/json")])
