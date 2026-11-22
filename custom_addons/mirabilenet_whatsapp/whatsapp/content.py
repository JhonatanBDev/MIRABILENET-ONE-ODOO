"""Contenido de las conversaciones: limpieza, validación y traducción desde Meta.

Portado del sistema anterior (conversaciones.py) sin cambiar límites ni mensajes:
los flujos de n8n dependen de ellos. No importa Odoo.
"""
import re
import unicodedata

MAX_TEXT = 4096
MAX_INTERACTIVE_TEXT = 1024
MAX_BUTTONS = 3
MAX_BUTTON_TITLE = 20
MAX_FOOTER = 60
MAX_OPTION_ID = 200
MAX_LIST_ROWS = 10
MAX_ROW_TITLE = 24
MAX_ROW_DESCRIPTION = 72
MAX_SECTIONS = 10
MAX_ATTACHMENT = 5 * 1024 * 1024
MAX_ATTACHMENT_TEXT = 1024
BOT_HOURLY_LIMIT = 30
WINDOW_HOURS = 24

HANDOFF_NOTICE = (
    "Listo: el asistente automático se cerró en este chat y tu solicitud ya "
    "quedó enviada: una persona de nuestro equipo te va a contactar por este "
    "mismo chat en horario de atención."
)

SIGNATURES = {
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "application/pdf": b"%PDF-",
}
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf"}

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class SendRejected(Exception):
    """El envío no procede. `code` es estable para que n8n decida qué hacer."""

    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def clean_text(value, maximum):
    """Texto sin caracteres de control, normalizado y recortado."""
    text = unicodedata.normalize("NFC", "" if value is None else str(value))
    text = _CONTROL.sub("", text).replace("\r\n", "\n").strip()
    return text[:maximum]


def real_type(content):
    """Tipo según la firma del archivo, o None si no es uno permitido."""
    for mime, signature in SIGNATURES.items():
        if content.startswith(signature):
            return mime
    return None


def safe_file_name(name, mime):
    name = str(name or "adjunto").replace("\\", "/").split("/")[-1]
    name = re.sub(r'[\r\n"\\]', "_", clean_text(name, 120)).strip(" .") or "adjunto"
    name = name.rsplit(".", 1)[0].strip(" .") or "adjunto"
    extension = EXTENSIONS[mime]
    return "%s%s" % (name[:120 - len(extension)], extension)


def _option(raw, max_title, field):
    if not isinstance(raw, dict):
        raise ValueError("Cada elemento de '%s' debe ser un objeto con id y titulo." % field)
    ident = clean_text(raw.get("id"), MAX_OPTION_ID)
    title = clean_text(raw.get("titulo"), 200)
    if not ident or not title:
        raise ValueError("Cada elemento de '%s' necesita id y titulo." % field)
    if len(title) > max_title:
        raise ValueError("El titulo '%s' supera %d caracteres." % (title, max_title))
    return {"id": ident, "titulo": title}


def validate_content(kind, data):
    """Valida y normaliza lo que n8n pide enviar. Lanza ValueError con el motivo."""
    if not isinstance(data, dict):
        raise ValueError("El contenido debe ser un objeto.")
    if kind == "texto":
        text = clean_text(data.get("texto"), MAX_TEXT + 1)
        if not text:
            raise ValueError("Falta el texto.")
        if len(text) > MAX_TEXT:
            raise ValueError("El texto supera %d caracteres." % MAX_TEXT)
        return {"texto": text}
    if kind not in ("botones", "lista"):
        raise ValueError("Tipo no soportado: use texto, botones o lista.")
    text = clean_text(data.get("texto"), MAX_INTERACTIVE_TEXT + 1)
    if not text:
        raise ValueError("Falta el texto que acompana a las opciones.")
    if len(text) > MAX_INTERACTIVE_TEXT:
        raise ValueError("El texto supera %d caracteres." % MAX_INTERACTIVE_TEXT)
    if kind == "botones":
        raw = data.get("botones")
        if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_BUTTONS:
            raise ValueError("Se necesitan entre 1 y %d botones." % MAX_BUTTONS)
        buttons = [_option(b, MAX_BUTTON_TITLE, "botones") for b in raw]
        if len({b["id"] for b in buttons}) != len(buttons):
            raise ValueError("Los botones no pueden repetir id.")
        footer = clean_text(data.get("pie"), MAX_FOOTER + 1)
        if len(footer) > MAX_FOOTER:
            raise ValueError("El pie supera %d caracteres." % MAX_FOOTER)
        result = {"texto": text, "botones": buttons}
        if footer:
            result["pie"] = footer
        return result
    listing = data.get("lista")
    if not isinstance(listing, dict):
        raise ValueError("Falta la lista.")
    button = clean_text(listing.get("boton"), 200)
    if not button or len(button) > MAX_BUTTON_TITLE:
        raise ValueError(
            "El boton de la lista es obligatorio y de hasta %d caracteres." % MAX_BUTTON_TITLE)
    raw_sections = listing.get("secciones")
    if not isinstance(raw_sections, list) or not 1 <= len(raw_sections) <= MAX_SECTIONS:
        raise ValueError("La lista necesita entre 1 y %d secciones." % MAX_SECTIONS)
    sections, ids = [], set()
    for section in raw_sections:
        if (not isinstance(section, dict) or not isinstance(section.get("filas"), list)
                or not section["filas"]):
            raise ValueError("Cada seccion necesita al menos una fila.")
        rows = []
        for raw_row in section["filas"]:
            row = _option(raw_row, MAX_ROW_TITLE, "filas")
            description = clean_text(raw_row.get("descripcion"), MAX_ROW_DESCRIPTION + 1)
            if len(description) > MAX_ROW_DESCRIPTION:
                raise ValueError(
                    "La descripcion supera %d caracteres." % MAX_ROW_DESCRIPTION)
            if description:
                row["descripcion"] = description
            rows.append(row)
            ids.add(row["id"])
        sections.append({"titulo": clean_text(section.get("titulo"), MAX_ROW_TITLE),
                         "filas": rows})
    total = sum(len(s["filas"]) for s in sections)
    if total > MAX_LIST_ROWS:
        raise ValueError("La lista admite hasta %d filas en total." % MAX_LIST_ROWS)
    if len(ids) != total:
        raise ValueError("Las filas no pueden repetir id.")
    return {"texto": text, "lista": {"boton": button, "secciones": sections}}


def normalize_meta_incoming(incoming):
    """Traduce un mensaje de Meta a (tipo, texto, datos). Del adjunto solo se anota el tipo
    de archivo: el archivo lo descarga y valida quien guarda el comprobante."""
    kind = incoming.get("type", "")
    if kind == "text":
        return "texto", clean_text((incoming.get("text") or {}).get("body"), MAX_TEXT), {}
    if kind == "interactive":
        inter = incoming.get("interactive") or {}
        chosen = inter.get("button_reply") or inter.get("list_reply") or {}
        return "respuesta", clean_text(chosen.get("title"), 200), {
            "opcion_id": clean_text(chosen.get("id"), MAX_OPTION_ID)}
    if kind == "button":
        button = incoming.get("button") or {}
        return "respuesta", clean_text(button.get("text"), 200), {
            "opcion_id": clean_text(button.get("payload"), MAX_OPTION_ID)}
    if kind == "location":
        place = incoming.get("location") or {}
        try:
            lat, lng = float(place.get("latitude")), float(place.get("longitude"))
        except (TypeError, ValueError):
            return "otro", "", {"tipo_meta": "location"}
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return "otro", "", {"tipo_meta": "location"}
        return "ubicacion", "", {
            "latitud": round(lat, 6), "longitud": round(lng, 6),
            "nombre": clean_text(place.get("name"), 200),
            "direccion": clean_text(place.get("address"), 300)}
    if kind in ("image", "document"):
        attachment = incoming.get(kind) or {}
        return ("imagen" if kind == "image" else "documento"), \
            clean_text(attachment.get("caption"), 1000), {
                "mime": clean_text(attachment.get("mime_type"), 80)}
    return "otro", "", {"tipo_meta": clean_text(kind, 40)}
