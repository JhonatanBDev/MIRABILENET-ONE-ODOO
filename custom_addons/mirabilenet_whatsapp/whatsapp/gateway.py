"""Puerta única hacia Meta.

Los modelos nunca llaman al Graph API directamente: piden las operaciones aquí.
RealMetaGateway usa el cliente del sistema anterior (cloud_api.py, sin cambios);
FakeMetaGateway es un doble en memoria para desarrollo y pruebas.
"""
from . import cloud_api
from .cloud_api import WhatsAppError  # noqa: F401  (se reexporta)


class MetaGateway:
    def send_template(self, **kwargs):
        """Envía una plantilla aprobada. Devuelve el id del mensaje en Meta."""
        raise NotImplementedError

    def send_session(self, **kwargs):
        """Envía un mensaje dentro de la ventana de 24 horas."""
        raise NotImplementedError

    def describe_number(self, **kwargs):
        raise NotImplementedError

    def download_media(self, **kwargs):
        raise NotImplementedError

    def upload_media(self, **kwargs):
        raise NotImplementedError


class RealMetaGateway(MetaGateway):

    def send_template(self, **kwargs):
        return cloud_api.enviar_plantilla(**kwargs)

    def send_session(self, **kwargs):
        return cloud_api.enviar_sesion(**kwargs)

    def describe_number(self, **kwargs):
        return cloud_api.describir_numero(**kwargs)

    def download_media(self, **kwargs):
        return cloud_api.descargar_media(**kwargs)

    def upload_media(self, **kwargs):
        return cloud_api.subir_media(**kwargs)


class FakeMetaGateway(MetaGateway):
    """Meta en memoria. `sent` guarda lo enviado; `failures` son errores a devolver."""

    sent = []
    failures = []
    media = {}
    numbers = {}
    counter = 0

    @classmethod
    def reset(cls):
        cls.sent, cls.failures, cls.media, cls.numbers, cls.counter = [], [], {}, {}, 0

    @classmethod
    def fail_next(cls, message="Fallo simulado", code="", retryable=False):
        cls.failures.append(WhatsAppError(message, codigo=code, reintentable=retryable))

    def _next(self, kind, payload):
        cls = type(self)
        if cls.failures:
            raise cls.failures.pop(0)
        cls.counter += 1
        message_id = "wamid.FAKE%05d" % cls.counter
        cls.sent.append(dict(payload, kind=kind, id=message_id))
        return message_id

    def send_template(self, **kwargs):
        if kwargs.get("requiere_imagen_encabezado") and not kwargs.get("header_image_url"):
            raise WhatsAppError("La plantilla requiere una imagen en el encabezado.")
        return self._next("template", kwargs)

    def send_session(self, **kwargs):
        cloud_api.cuerpo_de_sesion(kwargs["destino"], kwargs["tipo"], kwargs["contenido"])
        return self._next("session", kwargs)

    def describe_number(self, **kwargs):
        cls = type(self)
        if cls.failures:
            raise cls.failures.pop(0)
        return dict(cls.numbers.get(kwargs["phone_number_id"], {
            "display_phone_number": "+591 70000000", "verified_name": "Prueba"}))

    def download_media(self, **kwargs):
        cls = type(self)
        if kwargs["media_id"] not in cls.media:
            raise WhatsAppError("Archivo inexistente.", http_status=404)
        return cls.media[kwargs["media_id"]]

    def upload_media(self, **kwargs):
        return self._next("media", {"nombre": kwargs.get("nombre")})
