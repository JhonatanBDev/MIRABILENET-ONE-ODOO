"""Entrega de eventos a n8n, firmados igual que en el sistema anterior.

n8n no cambia: recibe el mismo cuerpo, la misma cabecera de firma y un JWT HS256 de
dos minutos que lleva el SHA-256 del cuerpo. Los secretos viven en el entorno del
servidor, fuera de la base:

    MIRABILENET_N8N_API_TOKEN       token que presenta n8n (credencial «MIRABILENET API»)
    MIRABILENET_N8N_WEBHOOK_SECRET  secreto de la firma («MIRABILENET Webhook (JWT)»)

No importa Odoo.
"""
import base64
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen

TOKEN_ENV = "MIRABILENET_N8N_API_TOKEN"
SECRET_ENV = "MIRABILENET_N8N_WEBHOOK_SECRET"
DEFAULT_INTERNAL_HOSTS = ("n8n", "localhost", "127.0.0.1")
JWT_LIFETIME = 120
TIMEOUT = 10


class N8NError(Exception):
    pass


def api_token():
    return os.environ.get(TOKEN_ENV, "")


def webhook_secret():
    return os.environ.get(SECRET_ENV, "")


def token_matches(presented):
    """El token de n8n, comparado en tiempo constante. Sin token configurado, nadie entra."""
    expected = api_token()
    presented = presented or ""
    if presented.lower().startswith("bearer "):
        presented = presented[7:].strip()
    return bool(expected) and bool(presented) and hmac.compare_digest(
        presented.encode(), expected.encode())


def encode_body(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def make_jwt(secret, body, now=None):
    """JWT HS256 de vida corta con el hash del cuerpo: robado, no sirve con otro contenido."""
    now = int(now if now is not None else time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = _b64(json.dumps(
        {"iss": "mirabilenet", "iat": now, "exp": now + JWT_LIFETIME,
         "sha256": hashlib.sha256(body).hexdigest()}, separators=(",", ":")).encode())
    signing = header + b"." + claims
    signature = _b64(hmac.new(secret.encode(), signing, hashlib.sha256).digest())
    return (signing + b"." + signature).decode()


def headers_for(secret, body, now=None):
    return {
        "Content-Type": "application/json",
        "X-Mirabilenet-Signature": "sha256=%s" % hmac.new(
            secret.encode(), body, hashlib.sha256).hexdigest(),
        "Authorization": "Bearer %s" % make_jwt(secret, body, now),
    }


def check_url(url, internal_hosts=DEFAULT_INTERNAL_HOSTS):
    """HTTPS siempre, salvo HTTP hacia un nombre de la red interna."""
    target = urlparse(url or "")
    local_http = target.scheme == "http" and target.hostname in set(internal_hosts)
    if target.scheme != "https" and not local_http:
        raise N8NError("URL n8n insegura: se requiere HTTPS.")
    return True


class N8NClient:
    def post(self, url, payload, secret, internal_hosts=DEFAULT_INTERNAL_HOSTS):
        raise NotImplementedError


class RealN8NClient(N8NClient):

    def post(self, url, payload, secret, internal_hosts=DEFAULT_INTERNAL_HOSTS):
        check_url(url, internal_hosts)
        body = encode_body(payload)
        request = Request(url, data=body, method="POST")
        for name, value in headers_for(secret, body).items():
            request.add_header(name, value)
        try:
            with urlopen(request, timeout=TIMEOUT) as response:
                if not 200 <= response.status < 300:
                    raise N8NError("Webhook n8n respondio HTTP %s" % response.status)
        except N8NError:
            raise
        except Exception as exc:
            raise N8NError(str(getattr(exc, "code", "") or type(exc).__name__))
        return True


class FakeN8NClient(N8NClient):
    """n8n en memoria: guarda lo recibido tal como viajaría por la red."""

    received = []
    failures = []

    @classmethod
    def reset(cls):
        cls.received, cls.failures = [], []

    def post(self, url, payload, secret, internal_hosts=DEFAULT_INTERNAL_HOSTS):
        check_url(url, internal_hosts)
        cls = type(self)
        if cls.failures:
            raise N8NError(cls.failures.pop(0))
        body = encode_body(payload)
        cls.received.append({"url": url, "body": body, "headers": headers_for(secret, body),
                             "payload": json.loads(body.decode())})
        return True
