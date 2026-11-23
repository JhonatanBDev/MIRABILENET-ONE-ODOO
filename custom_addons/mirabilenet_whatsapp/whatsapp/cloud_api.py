"""Cliente del Graph API de Meta para WhatsApp Cloud API.

Se usa `urllib` de la biblioteca estandar y no `requests` a proposito: la imagen
del worker no trae `requests` y esta integracion no justifica sumar una
dependencia — son dos llamadas POST y una GET.

El cliente no sabe nada de avisos de cobro ni de sucursales. Recibe un
`phone_number_id`, un destino y una plantilla ya resuelta. Toda la traduccion
de negocio ocurre en `services.py`.
"""

import json
import logging
import re
import socket
import uuid
from urllib.parse import urlparse
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

BASE = "https://graph.facebook.com"
TIMEOUT = 15


class WhatsAppError(Exception):
    """Fallo al hablar con Meta.

    `codigo` es el codigo de error de Meta cuando lo hay. Importa porque
    distingue lo reintentable (429, 5xx, 131026 destino no disponible) de lo
    definitivo (132001 plantilla inexistente), y de eso depende si la tarea
    reintenta o marca la fila como fallida.
    """

    def __init__(self, mensaje, codigo="", http_status=None, reintentable=False):
        super().__init__(mensaje)
        self.codigo = str(codigo or "")
        self.http_status = http_status
        self.reintentable = reintentable


#: Errores de Meta que se resuelven solos o con espera. Todo lo demas se
#: considera definitivo: reintentar una plantilla mal escrita 3 veces solo
#: retrasa el aviso al operador.
CODIGOS_REINTENTABLES = {
    "0",       # error temporal sin clasificar
    "1",       # API desconocida
    "2",       # servicio temporalmente no disponible
    "4",       # limite de peticiones de la aplicacion
    "80007",   # limite de la cuenta WABA
    "130429",  # limite de mensajes por segundo
    "131000",  # error generico del servidor
    "131026",  # el destino no puede recibir el mensaje ahora
    "131048",  # limite por calidad del remitente
    "131056",  # demasiados mensajes al mismo destino
}


def _peticion(metodo, url, token, cuerpo=None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, method=metodo)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            return json.loads(res.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        crudo = exc.read().decode(errors="replace")
        try:
            detalle = json.loads(crudo).get("error", {})
        except json.JSONDecodeError:
            detalle = {}
        codigo = str(detalle.get("code", ""))
        mensaje = detalle.get("message") or crudo[:300] or f"HTTP {exc.code}"
        raise WhatsAppError(
            mensaje,
            codigo=codigo,
            http_status=exc.code,
            # 5xx y 429 son de Meta, no del contenido del mensaje.
            reintentable=(
                exc.code >= 500 or exc.code == 429 or codigo in CODIGOS_REINTENTABLES
            ),
        ) from exc
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        raise WhatsAppError(
            f"No se pudo contactar con Meta: {exc}", reintentable=True
        ) from exc


def enviar_plantilla(
    *, phone_number_id, token, destino, plantilla, idioma, parametros,
    header_image_url="", requiere_imagen_encabezado=False,
    parameter_format="POSITIONAL", parameter_names=None, api_version="v21.0", botones=None
):
    """Envia un mensaje de plantilla. Devuelve el `wa_message_id`.

    `parametros` contiene los valores del cuerpo en el orden configurado en la
    plantilla. POSITIONAL usa {{1}}, {{2}}...; NAMED añade `parameter_name` a
    cada parámetro. Los nombres se validan contra los declarados en Meta.
    """
    formato = str(parameter_format or "POSITIONAL").upper()
    if formato not in {"POSITIONAL", "NAMED"}:
        raise WhatsAppError(f"Formato de parametros no soportado: {formato}.")
    if requiere_imagen_encabezado and not header_image_url:
        raise WhatsAppError(
            "La plantilla requiere una imagen en el encabezado, pero no hay un QR disponible."
        )

    valores = []
    for bruto in parametros or []:
        texto = "" if bruto is None else str(bruto)
        texto = re.sub(r"\s+", " ", texto).strip()
        # Meta no acepta parámetros vacíos. El guion hace explícito que ese
        # dato no estaba disponible, y evita mandar null o una cadena vacía.
        valores.append(texto or "-")

    nombres = list(parameter_names or [])
    if formato == "NAMED":
        if len(nombres) != len(valores):
            raise WhatsAppError(
                "La plantilla NAMED necesita un nombre por cada parámetro del cuerpo."
            )
        if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", str(n or "")) for n in nombres):
            raise WhatsAppError(
                "Los nombres de parámetros NAMED deben empezar con una letra y "
                "contener solo letras, números o guion bajo."
            )

    url = f"{BASE}/{api_version}/{phone_number_id}/messages"
    cuerpo = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": destino,
        "type": "template",
        "template": {
            "name": plantilla,
            "language": {"code": idioma},
        },
    }
    componentes = []
    if header_image_url:
        componentes.append({
            "type": "header",
            "parameters": [{"type": "image", "image": {"link": header_image_url}}],
        })
    if parametros:
        componentes.append({
            "type": "body",
            "parameters": [
                {
                    **({"parameter_name": str(nombres[i])} if formato == "NAMED" else {}),
                    "type": "text",
                    "text": valores[i],
                }
                for i in range(len(valores))
            ],
        })
    # Botones de respuesta rápida de la plantilla: cada uno lleva el dato que vuelve en la
    # respuesta (button.payload), en el mismo orden en que se declararon en Meta.
    for indice, payload in enumerate(botones or []):
        componentes.append({
            "type": "button", "sub_type": "quick_reply", "index": str(indice),
            "parameters": [{"type": "payload", "payload": str(payload)[:256]}],
        })
    if componentes:
        cuerpo["template"]["components"] = componentes

    # El payload incluye el teléfono y el contenido del aviso; se deja en DEBUG
    # para diagnosticar fallos temporalmente, y nunca incluye el access token.
    log.debug(
        "WhatsApp Cloud API payload: %s",
        json.dumps(cuerpo, ensure_ascii=False, separators=(",", ":")),
    )
    respuesta = _peticion("POST", url, token, cuerpo)
    mensajes = respuesta.get("messages") or []
    if not mensajes:
        raise WhatsAppError(f"Meta acepto la peticion sin devolver mensaje: {respuesta}")
    return mensajes[0].get("id", "")


def cuerpo_de_sesion(destino, tipo, contenido) -> dict:
    """Payload de Meta para un mensaje dentro de la ventana de 24 horas.

    `contenido` ya viene validado por `conversaciones.validar_contenido`: aqui
    solo se traduce a la forma que pide Meta.
    """
    base = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": destino}
    if tipo == "texto":
        return {**base, "type": "text", "text": {"body": contenido["texto"], "preview_url": False}}
    if tipo == "imagen":
        imagen = {"id": contenido["media_id"]}
        if contenido.get("texto"):
            imagen["caption"] = contenido["texto"]
        return {**base, "type": "image", "image": imagen}
    if tipo == "documento":
        documento = {
            "id": contenido["media_id"],
            "filename": contenido["archivo_nombre"],
        }
        if contenido.get("texto"):
            documento["caption"] = contenido["texto"]
        return {**base, "type": "document", "document": documento}
    if tipo == "botones":
        interactivo = {
            "type": "button",
            "body": {"text": contenido["texto"]},
            "action": {"buttons": [
                {"type": "reply", "reply": {"id": b["id"], "title": b["titulo"]}}
                for b in contenido["botones"]
            ]},
        }
        if contenido.get("pie"):
            interactivo["footer"] = {"text": contenido["pie"]}
        return {**base, "type": "interactive", "interactive": interactivo}
    if tipo == "lista":
        lista = contenido["lista"]
        return {**base, "type": "interactive", "interactive": {
            "type": "list",
            "body": {"text": contenido["texto"]},
            "action": {
                "button": lista["boton"],
                "sections": [
                    {"title": s["titulo"], "rows": [
                        {"id": f["id"], "title": f["titulo"],
                         **({"description": f["descripcion"]} if f.get("descripcion") else {})}
                        for f in s["filas"]
                    ]}
                    for s in lista["secciones"]
                ],
            },
        }}
    raise WhatsAppError(f"Tipo de mensaje de sesion no soportado: {tipo}.")


def enviar_sesion(*, phone_number_id, token, destino, tipo, contenido, api_version="v21.0"):
    """Envia un mensaje de sesion (sin plantilla). Devuelve el `wa_message_id`."""
    url = f"{BASE}/{api_version}/{phone_number_id}/messages"
    respuesta = _peticion("POST", url, token, cuerpo_de_sesion(destino, tipo, contenido))
    mensajes = respuesta.get("messages") or []
    if not mensajes:
        raise WhatsAppError(f"Meta acepto la peticion sin devolver mensaje: {respuesta}")
    return mensajes[0].get("id", "")


def subir_media(*, phone_number_id, token, contenido, mime, nombre, api_version="v21.0"):
    """Sube una imagen/PDF a Meta y devuelve su media ID para el mensaje."""
    boundary = f"----Mirabilenet{uuid.uuid4().hex}"
    nombre_seguro = re.sub(r"[^A-Za-z0-9._-]", "_", str(nombre))[:120] or "adjunto"
    partes = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"messaging_product\"\r\n\r\nwhatsapp\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\n{mime}\r\n".encode(),
        (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{nombre_seguro}\"\r\nContent-Type: {mime}\r\n\r\n"
        ).encode(),
        contenido,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    url = f"{BASE}/{api_version}/{phone_number_id}/media"
    req = urllib.request.Request(url, data=b"".join(partes), method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            respuesta = json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        crudo = exc.read().decode(errors="replace")
        try:
            detalle = json.loads(crudo).get("error", {})
        except json.JSONDecodeError:
            detalle = {}
        codigo = str(detalle.get("code", ""))
        mensaje = detalle.get("message") or crudo[:300] or f"HTTP {exc.code}"
        raise WhatsAppError(
            mensaje, codigo=codigo, http_status=exc.code,
            reintentable=exc.code >= 500 or exc.code == 429 or codigo in CODIGOS_REINTENTABLES,
        ) from exc
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        raise WhatsAppError(f"No se pudo cargar el archivo a Meta: {exc}", reintentable=True) from exc
    media_id = respuesta.get("id")
    if not media_id:
        raise WhatsAppError("Meta no devolvió el ID del archivo cargado.")
    return media_id


def descargar_media(*, media_id, token, api_version="v21.0", max_bytes=5 * 1024 * 1024):
    """Descarga un archivo entrante de Meta con limite de tamano y host."""
    metadata = _peticion(
        "GET", f"{BASE}/{api_version}/{media_id}", token
    )
    url = metadata.get("url", "")
    host = urlparse(url)
    if host.scheme != "https" or not host.hostname or not (
        host.hostname == "facebook.com"
        or host.hostname.endswith(".facebook.com")
        or host.hostname.endswith(".fbsbx.com")
        or host.hostname.endswith(".fbcdn.net")
        or host.hostname.endswith(".facebook.net")
    ):
        raise WhatsAppError("Meta devolvio una URL de archivo no permitida.")
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            contenido = response.read(max_bytes + 1)
            if len(contenido) > max_bytes:
                raise WhatsAppError("El comprobante supera el tamano permitido.")
            mime = response.headers.get_content_type()
            return contenido, mime
    except urllib.error.HTTPError as exc:
        raise WhatsAppError(
            f"Meta no permitio descargar el archivo (HTTP {exc.code}).",
            http_status=exc.code, reintentable=exc.code >= 500 or exc.code == 429,
        ) from exc
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        raise WhatsAppError("No se pudo descargar el comprobante.", reintentable=True) from exc


#: Campos que Meta ha expuesto siempre para un numero.
CAMPOS_BASE = "display_phone_number,verified_name,quality_rating,code_verification_status"

#: Campos que delatan si el numero esta en coexistencia. Van en una consulta
#: aparte porque el Graph API responde con error cuando se le pide un campo que
#: su version no conoce: mezclarlos con los de arriba haria que la verificacion
#: entera fallara en cuentas donde esos campos todavia no existen.
CAMPOS_PLATAFORMA = "platform_type,is_on_biz_app"


def describir_numero(*, phone_number_id, token, api_version="v21.0"):
    """Lee el numero en Meta. Se usa para el boton Verificar del panel.

    Confirma tres cosas de una vez: que el token sirve, que el
    `phone_number_id` existe y que pertenece a esta cuenta.

    Intenta ademas averiguar si el numero esta en coexistencia, pero ese dato
    es opcional: si Meta no lo expone, la verificacion igual se da por buena.
    """
    url = f"{BASE}/{api_version}/{phone_number_id}?fields={CAMPOS_BASE}"
    datos = _peticion("GET", url, token)

    try:
        extra = _peticion(
            "GET",
            f"{BASE}/{api_version}/{phone_number_id}?fields={CAMPOS_PLATAFORMA}",
            token,
        )
    except WhatsAppError as exc:
        log.info("Meta no expone los campos de plataforma: %s", exc)
    else:
        datos.update({k: v for k, v in extra.items() if k != "id"})

    return datos


def plataforma_de(datos: dict) -> str:
    """Resume en una cadena lo que Meta dijo sobre la plataforma del numero.

    Cadena vacia cuando Meta no informa nada, que es distinto de informar que
    el numero NO esta en la app: no hay que confundir 'no se' con 'no'.
    """
    partes = []
    if datos.get("platform_type"):
        partes.append(str(datos["platform_type"]))
    if "is_on_biz_app" in datos:
        partes.append(
            "en app de negocio" if datos["is_on_biz_app"] else "solo nube"
        )
    return " · ".join(partes)


def sugiere_coexistencia(datos: dict) -> bool | None:
    """True/False segun Meta, o None si Meta no dio informacion suficiente."""
    if "is_on_biz_app" in datos:
        return bool(datos["is_on_biz_app"])
    tipo = str(datos.get("platform_type", "")).upper()
    if not tipo:
        return None
    return "SMB_APP" in tipo or "COEXIST" in tipo


def listar_plantillas(*, waba_id, token, api_version="v21.0", limite=100):
    """Plantillas de la cuenta con su estado de aprobacion."""
    url = (
        f"{BASE}/{api_version}/{waba_id}/message_templates"
        f"?fields=name,status,language,category,components&limit={limite}"
    )
    return _peticion("GET", url, token).get("data", [])
