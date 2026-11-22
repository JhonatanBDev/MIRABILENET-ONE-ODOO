"""Normalización de teléfonos y de textos entrantes. No importa Odoo."""
import re
import unicodedata

DEFAULT_COUNTRY = "591"
#: Bolivia: los móviles tienen 8 dígitos y empiezan en 6 o 7. Los fijos no reciben WhatsApp.
MOBILE_PREFIXES = ("6", "7")

#: Palabras con las que el cliente pide no recibir más mensajes. No pasan por persuasión.
OPT_OUT_WORDS = {
    "baja", "stop", "salir", "unsubscribe", "cancelar mensajes",
    "dejar de recibir mensajes", "no quiero recibir mensajes", "no mas mensajes",
}


class NotSendable(Exception):
    """El mensaje no se puede encolar. No es un error: es una decisión."""


def normalize_number(raw, country=DEFAULT_COUNTRY):
    """Número en E.164 sin el signo +, como lo pide Meta.

    Acepta lo que escriben los operadores: '71006044', '+591 71006044',
    '00591-71006044', '(591) 7100 6044'.
    """
    if not raw:
        raise NotSendable("El cliente no tiene número de WhatsApp.")
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        raise NotSendable("Número sin dígitos: %r" % raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 8:
        if digits[0] not in MOBILE_PREFIXES:
            raise NotSendable(
                "%r no parece un móvil boliviano: WhatsApp no llega a fijos." % raw)
        digits = country + digits
    if not digits.startswith(country) and len(digits) <= 9:
        raise NotSendable("Número incompleto o ambiguo: %r" % raw)
    if not 10 <= len(digits) <= 15:
        raise NotSendable("Número de longitud inválida: %r" % raw)
    return digits


def plain_text(text):
    """Minúsculas, sin tildes ni signos: para reconocer palabras clave."""
    lowered = unicodedata.normalize("NFKD", (text or "").strip().lower())
    return re.sub(r"[^a-z0-9\s]", "", lowered.encode("ascii", "ignore").decode())


def is_opt_out(text):
    return plain_text(text) in OPT_OUT_WORDS


def clean_parameter(value):
    """Meta rechaza un parámetro vacío, con saltos de línea o con espacios dobles."""
    cleaned = re.sub(r"\s+", " ", "" if value is None else str(value)).strip()
    return cleaned or "-"
