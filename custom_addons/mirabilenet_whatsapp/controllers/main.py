import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime

from odoo import http
from odoo.http import request

from ..whatsapp.gateway import WhatsAppError

_logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/api/v1/messaging/whatsapp/webhook"
ECHO_FIELDS = {"smb_message_echoes", "message_echoes"}
MAX_BODY = 2 * 1024 * 1024


def _moment(item):
    """Meta manda la marca de tiempo en segundos Unix, como texto."""
    try:
        return datetime.utcfromtimestamp(int(item.get("timestamp")))
    except (TypeError, ValueError):
        return datetime.utcnow()


class MirabilenetWhatsappWebhook(http.Controller):

    @http.route(WEBHOOK_PATH, type="http", auth="public", methods=["GET", "POST"],
                csrf=False, save_session=False)
    def webhook(self, **params):
        """Lo llama Meta, no el panel. Se autentica de dos formas: el alta devuelve el
        desafío solo si el token coincide, y cada POST trae un HMAC del cuerpo con el
        secreto de la aplicación. Sin firma válida no se toca la base."""
        env = request.env
        settings = env["mirabilenet.whatsapp.settings"].sudo()._load()
        if request.httprequest.method == "GET":
            try:
                expected = settings._secret("webhook_verify_token")
            except WhatsAppError:
                expected = ""
            token = params.get("hub.verify_token") or ""
            if (params.get("hub.mode") == "subscribe" and expected
                    and hmac.compare_digest(token, expected)):
                return request.make_response(
                    params.get("hub.challenge") or "", headers=[("Content-Type", "text/plain")])
            _logger.warning("Alta de webhook rechazada: token incorrecto")
            return request.make_response("Token de verificacion incorrecto.", status=403)

        raw = request.httprequest.get_data(cache=False)
        try:
            secret = settings._secret("app_secret")
        except WhatsAppError:
            secret = ""
        if not secret:
            _logger.error("Webhook recibido sin secreto de aplicación: se descarta.")
            return request.make_response("Webhook sin secreto configurado.", status=403)
        header = request.httprequest.headers.get("X-Hub-Signature-256", "")
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not header.startswith("sha256=") or not hmac.compare_digest(header[7:], expected):
            _logger.warning("Webhook con firma inválida desde %s",
                            request.httprequest.remote_addr)
            return request.make_response("Firma invalida.", status=403)
        if len(raw) > MAX_BODY:
            return self._json({"detail": "cuerpo demasiado grande"}, 413)
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return self._json({"detail": "cuerpo ilegible"}, 400)
        env["mirabilenet.whatsapp.message"].sudo()._process_webhook(body)
        return self._json({"ok": True})

    def _json(self, body, status=200):
        return request.make_response(
            json.dumps(body), status=status, headers=[("Content-Type", "application/json")])

    @http.route("/mirabilenet/qr/<string:token>.png", type="http", auth="public",
                methods=["GET"], csrf=False, save_session=False)
    def payment_qr(self, token, **_kwargs):
        """El QR de pago que Meta descarga para el encabezado de la plantilla. La clave del
        nombre no se adivina; un QR reemplazado sigue disponible para avisos ya enviados."""
        qr = request.env["mirabilenet.payment.qr"].sudo().with_context(
            active_test=False).search([("token", "=", token)], limit=1)
        if not qr or not qr.image:
            return request.not_found()
        return request.make_response(base64.b64decode(qr.image), headers=[
            ("Content-Type", "image/png"), ("Cache-Control", "public, max-age=3600")])


def process_webhook(Message, body):
    """Estados de entrega, mensajes entrantes y actividad de personas. Devuelve un resumen."""
    env = Message.env
    summary = {"estados": 0, "bajas": 0, "ecos": 0, "entrantes": 0}
    Conversation = env["mirabilenet.conversation"].sudo()
    for entry in body.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            pnid = (value.get("metadata") or {}).get("phone_number_id") or ""
            for status in value.get("statuses") or []:
                summary["estados"] += int(bool(Message._apply_meta_status(status)))
            for incoming in value.get("messages") or []:
                handled = Conversation._process_meta_incoming(incoming, pnid)
                summary["entrantes"] += 1
                summary["bajas"] += int(handled == "baja")
            if change.get("field") in ECHO_FIELDS:
                number = env["mirabilenet.whatsapp.number"].sudo().search(
                    [("phone_number_id", "=", pnid)], limit=1)
                echoes = value.get("message_echoes") or value.get("smb_message_echoes") or []
                for echo in echoes if number else []:
                    contact = str(echo.get("to") or echo.get("recipient_id") or "").strip()
                    if contact:
                        env["mirabilenet.whatsapp.agent.activity"]._record_echo(
                            number, contact, _moment(echo))
                        summary["ecos"] += 1
    return summary
