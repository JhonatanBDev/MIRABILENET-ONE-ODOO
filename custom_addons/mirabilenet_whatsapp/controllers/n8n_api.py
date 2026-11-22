import json
import logging

from odoo import http
from odoo.http import request

from ..whatsapp import n8n

_logger = logging.getLogger(__name__)

BASE = "/api/v1/messaging/n8n"
CONV = BASE + "/conversations/<int:pk>"
MAX_BODY = 6 * 1024 * 1024


class MirabilenetN8nApiController(http.Controller):
    """Las mismas rutas que usaban los flujos de n8n en el sistema anterior.

    Se autentican con el token de la credencial «MIRABILENET API», no con una sesión.
    Sin token configurado en el servidor, la API queda cerrada.
    """

    def _reply(self, status, body):
        return request.make_response(
            json.dumps(body, ensure_ascii=False), status=status,
            headers=[("Content-Type", "application/json; charset=utf-8")])

    def _json_body(self):
        raw = request.httprequest.get_data(cache=False)
        if len(raw) > MAX_BODY:
            return None
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _call(self, method, *args, body=False, query=False):
        if not n8n.token_matches(request.httprequest.headers.get("Authorization", "")):
            return self._reply(403, {
                "detail": "Las credenciales de autenticación no se proveyeron."})
        extra = []
        if body:
            data = self._json_body()
            if data is None:
                return self._reply(400, {"detail": "Se esperaba un objeto JSON."})
            extra.append(data)
        if query:
            extra.append(dict(request.httprequest.args))
        api = request.env["mirabilenet.n8n.api"].sudo()
        try:
            status, payload = getattr(api, method)(*args, *extra)
        except Exception:
            _logger.exception("Error en la API de n8n (%s)", method)
            request.env.cr.rollback()
            return self._reply(500, {"detail": "Error interno."})
        return self._reply(status, payload)

    def _route(path, methods):  # noqa: N805  (decorador auxiliar)
        return http.route(path, type="http", auth="public", methods=methods, csrf=False,
                          save_session=False)

    @_route(BASE + "/charges", ["GET"])
    def charges(self, **_kw):
        return self._call("charges", query=True)

    @_route(BASE + "/customer", ["GET"])
    def customer(self, **_kw):
        return self._call("customer", query=True)

    @_route(BASE + "/reminders", ["POST"])
    def reminders(self, **_kw):
        return self._call("reminders", body=True)

    @_route(BASE + "/cases", ["POST"])
    def cases(self, **_kw):
        return self._call("cases", body=True)

    @_route(BASE + "/opt-outs", ["POST"])
    def opt_outs(self, **_kw):
        return self._call("opt_outs", body=True)

    @_route(BASE + "/proofs", ["POST"])
    def proof_upload(self, **_kw):
        """Único punto que recibe un formulario con archivo, no JSON."""
        if not n8n.token_matches(request.httprequest.headers.get("Authorization", "")):
            return self._reply(403, {
                "detail": "Las credenciales de autenticación no se proveyeron."})
        upload = request.httprequest.files.get("archivo")
        raw = upload.read(MAX_BODY) if upload else None
        status, payload = request.env["mirabilenet.n8n.api"].sudo().proof_upload(
            dict(request.httprequest.form), raw, upload.mimetype if upload else "")
        return self._reply(status, payload)

    @_route(CONV, ["GET"])
    def conversation(self, pk, **_kw):
        return self._call("conversation", pk)

    @_route(CONV + "/charges", ["GET"])
    def conversation_charges(self, pk, **_kw):
        return self._call("conversation_charges", pk)

    @_route(CONV + "/history", ["GET"])
    def conversation_history(self, pk, **_kw):
        return self._call("conversation_history", pk, query=True)

    @_route(CONV + "/proofs", ["GET"])
    def conversation_proofs(self, pk, **_kw):
        return self._call("conversation_proofs", pk)

    @_route(CONV + "/service", ["GET"])
    def conversation_service(self, pk, **_kw):
        return self._call("conversation_service", pk)

    @_route(CONV + "/handoff", ["POST"])
    def conversation_handoff(self, pk, **_kw):
        return self._call("conversation_handoff", pk, body=True)

    @_route(CONV + "/qr", ["POST"])
    def conversation_qr(self, pk, **_kw):
        return self._call("conversation_qr", pk, body=True)

    @_route(CONV + "/organization", ["GET"])
    def conversation_organization(self, pk, **_kw):
        return self._call("conversation_organization", pk)

    @_route(CONV + "/plans", ["GET"])
    def conversation_plans(self, pk, **_kw):
        return self._call("conversation_plans", pk)

    @_route(CONV + "/retention-offers", ["GET"])
    def conversation_retention_offers(self, pk, **_kw):
        return self._call("conversation_retention_offers", pk)

    @_route(CONV + "/sales", ["GET"])
    def conversation_sales(self, pk, **_kw):
        return self._call("conversation_sales", pk)

    @_route(CONV + "/lead", ["POST"])
    def conversation_lead(self, pk, **_kw):
        return self._call("conversation_lead", pk, body=True)

    @_route(CONV + "/proofs/<int:proof_pk>/charge", ["POST"])
    def proof_charge(self, pk, proof_pk, **_kw):
        return self._call("proof_charge", pk, proof_pk, body=True)

    @_route(BASE + "/messages", ["POST"])
    def messages(self, **_kw):
        return self._call("messages", body=True)

    @_route(BASE + "/alerts", ["POST"])
    def alerts(self, **_kw):
        return self._call("alerts", body=True)

    @_route(BASE + "/ia/agotado", ["POST"])
    def ia_exhausted(self, **_kw):
        return self._call("ia_exhausted", body=True)
