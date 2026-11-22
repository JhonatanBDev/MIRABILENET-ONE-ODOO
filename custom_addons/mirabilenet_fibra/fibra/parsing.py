"""Lectura de los valores que llegan en los CSV del relevamiento."""
import csv
import io
import re
import unicodedata

#: Límites de Yapacaní. El asistente de importación permite cambiarlos por región.
DEFAULT_LAT_BOUNDS = (-17.5, -17.3)
DEFAULT_LON_BOUNDS = (-64.0, -63.8)

_ROUTE_CODE = re.compile(r"\(([^()]+)\)")


def normalize_key(text):
    """Clave comparable: minúsculas, sin acentos y con «_» en lugar de espacios o signos.

    «Color de hilo alimentador» → «color_de_hilo_alimentador»; «Zona/Barrio» → «zona_barrio».
    """
    text = (text or "").replace("﻿", "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def parse_coordinate(value, bounds=None):
    """Coordenada con los puntos de miles que deja la exportación.

    Regla: quitar todos los puntos (y comas), conservar el signo y poner el punto
    decimal después de los dos primeros dígitos. «-17.404.864» → -17.404864;
    «-6.388.524.129.690.300» → -63.8852412969030. Devuelve ``None`` si el texto no
    es un número o el resultado cae fuera de ``bounds`` (mínimo, máximo).
    """
    text = (value or "").strip().replace(" ", "")
    if not text:
        return None
    sign = -1 if text.startswith("-") else 1
    digits = text.lstrip("+-").replace(".", "").replace(",", "")
    if len(digits) < 2 or not digits.isdigit():
        return None
    number = sign * float("%s.%s" % (digits[:2], digits[2:] or "0"))
    if bounds and not bounds[0] <= number <= bounds[1]:
        return None
    return number


def parse_decimal(value):
    """Número con punto o coma decimal («3140.0», «3140,5», «1.234,5»). ``None`` si no hay."""
    text = (value or "").strip().replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        return float(text)
    except ValueError as error:
        raise ValueError("«%s» no es un número" % value) from error


def parse_integer(value):
    """Entero o ``None``. Acepta «16» y «16.0»."""
    number = parse_decimal(value)
    if number is None:
        return None
    if number != int(number):
        raise ValueError("«%s» no es un número entero" % value)
    return int(number)


def parse_route_codes(text):
    """Códigos entre paréntesis, en orden y sin repetir.

    «B1 (YAP-B-01), 1D (YAP-D-01)» → ["YAP-B-01", "YAP-D-01"].
    """
    codes = []
    for code in _ROUTE_CODE.findall(text or ""):
        code = code.strip()
        if code and code not in codes:
            codes.append(code)
    return codes


def read_csv(data, delimiter=";"):
    """Lee un CSV (bytes) del relevamiento.

    Devuelve ``(columnas, filas)``: las columnas normalizadas con :func:`normalize_key`
    y cada fila como diccionario ``{columna: texto}``, con su número de línea en
    ``"__line__"``. Acepta BOM, CRLF y filas vacías (se saltan).
    """
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
    else:
        text = data.lstrip("﻿")
    first_line = text.split("\n", 1)[0]
    if delimiter not in first_line and "," in first_line:
        delimiter = ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    header = None
    rows = []
    for line_number, cells in enumerate(reader, start=1):
        if not any((c or "").strip() for c in cells):
            continue
        if header is None:
            header = [normalize_key(c) for c in cells]
            continue
        row = {"__line__": line_number}
        for index, column in enumerate(header):
            if column:
                row[column] = (cells[index] if index < len(cells) else "").strip()
        rows.append(row)
    return header or [], rows


def normalize_choice(value, choices, aliases=None):
    """Valor de una lista de opciones a partir de un texto libre («Por verificar»)."""
    key = normalize_key(value)
    if not key:
        return None
    if key in choices:
        return key
    return (aliases or {}).get(key)
