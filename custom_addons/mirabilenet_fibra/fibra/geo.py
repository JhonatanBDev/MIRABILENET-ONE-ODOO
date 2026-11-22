"""Distancias, colores y el color de cada caja en el mapa."""
import json
import math

EARTH_RADIUS_M = 6371008.8

#: Color por defecto de cada tipo de tramo cuando el tramo no tiene uno propio.
DEFAULT_SEGMENT_COLORS = {
    "troncal": "#f57c00",
    "alimentador": "#8e24aa",
    "distribucion": "#43a047",
}
FALLBACK_SEGMENT_COLOR = "#ff9800"

#: Por debajo de esta proporción de puertos libres la caja está «casi llena».
NEARLY_FULL_RATIO = 0.25


def haversine(lat1, lon1, lat2, lon2):
    """Distancia en metros entre dos puntos."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def path_length(points):
    """Largo en metros de una lista de [lat, lon]."""
    return sum(haversine(a[0], a[1], b[0], b[1]) for a, b in zip(points, points[1:]))


def kml_color_to_hex(value):
    """Color KML «aabbggrr» → «#rrggbb». ``None`` si no es un color válido."""
    text = (value or "").strip().lstrip("#").lower()
    if len(text) == 6:
        text = "ff" + text
    if len(text) != 8 or any(c not in "0123456789abcdef" for c in text):
        return None
    return "#%s%s%s" % (text[6:8], text[4:6], text[2:4])


def segment_color(color, segment_type):
    """Color del tramo: el propio o el de su tipo."""
    return color or DEFAULT_SEGMENT_COLORS.get(segment_type, FALLBACK_SEGMENT_COLOR)


def nap_marker_status(state, port_count, ports_free):
    """Color del cuadrado de una caja en el mapa.

    ``danada`` (negro), ``sin_datos`` (gris: por verificar, inactiva o sin cantidad de
    puertos), ``llena`` (rojo), ``casi_llena`` (amarillo) o ``libre`` (verde).
    """
    if state == "danada":
        return "danada"
    if state in ("por_verificar", "inactiva") or not port_count:
        return "sin_datos"
    if ports_free <= 0:
        return "llena"
    if ports_free / port_count <= NEARLY_FULL_RATIO:
        return "casi_llena"
    return "libre"


def parse_geometry(text, lat_bounds=None, lon_bounds=None):
    """Lista de [lat, lon] guardada como JSON. ``ValueError`` si no es válida."""
    if not (text or "").strip():
        return []
    try:
        data = json.loads(text)
    except ValueError as error:
        raise ValueError("la geometría no es JSON válido") from error
    if not isinstance(data, list):
        raise ValueError("la geometría debe ser una lista de [lat, lon]")
    points = []
    for item in data:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            raise ValueError("cada vértice debe ser [lat, lon]")
        try:
            lat, lon = float(item[0]), float(item[1])
        except (TypeError, ValueError) as error:
            raise ValueError("vértice no numérico: %r" % (item,)) from error
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("vértice fuera del mundo: %r" % (item,))
        if lat_bounds and not lat_bounds[0] <= lat <= lat_bounds[1]:
            raise ValueError("latitud fuera de la zona: %s" % lat)
        if lon_bounds and not lon_bounds[0] <= lon <= lon_bounds[1]:
            raise ValueError("longitud fuera de la zona: %s" % lon)
        points.append([lat, lon])
    return points


def differs(old, new, tolerance=0.10):
    """``True`` si ``new`` se aparta de ``old`` más de ``tolerance`` (y ``old`` existe)."""
    if not old:
        return False
    return abs(new - old) / abs(old) > tolerance
