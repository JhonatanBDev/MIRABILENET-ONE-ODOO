"""Lectura de KML/KMZ de Google Earth: recorridos (LineString) y cajas (Point)."""
import io
import zipfile

from lxml import etree

from .geo import kml_color_to_hex


class KmlError(ValueError):
    pass


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _children(node, name):
    return [c for c in node if _local(c.tag) == name]


def _find(node, name):
    for element in node.iter():
        if _local(element.tag) == name:
            return element
    return None


def _text(node, name):
    found = _children(node, name)
    return (found[0].text or "").strip() if found and found[0].text else ""


def _coordinates(text):
    """«lon,lat,alt lon,lat,alt» → [[lat, lon], ...] (orden de Leaflet)."""
    points = []
    for chunk in (text or "").split():
        parts = chunk.split(",")
        if len(parts) < 2:
            continue
        try:
            lon, lat = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        points.append([lat, lon])
    return points


def _kml_bytes(data):
    if data[:2] == b"PK":
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as error:
            raise KmlError("El KMZ está dañado.") from error
        names = [n for n in archive.namelist() if n.lower().endswith(".kml")]
        if not names:
            raise KmlError("El KMZ no contiene ningún archivo KML.")
        names.sort(key=lambda n: (n.lower() != "doc.kml", n))
        return archive.read(names[0])
    return data


def _styles(root):
    """Color de línea por id de estilo (Style y StyleMap)."""
    colors = {}
    for style in root.iter():
        if _local(style.tag) != "Style" or not style.get("id"):
            continue
        line_style = _find(style, "LineStyle")
        if line_style is not None:
            color = kml_color_to_hex(_text(line_style, "color"))
            if color:
                colors[style.get("id")] = color
    for style_map in root.iter():
        if _local(style_map.tag) != "StyleMap" or not style_map.get("id"):
            continue
        for pair in _children(style_map, "Pair"):
            if _text(pair, "key") == "normal":
                target = _text(pair, "styleUrl").lstrip("#")
                if target in colors:
                    colors[style_map.get("id")] = colors[target]
    return colors


def parse_kml(data):
    """Placemarks de un KML o KMZ (bytes).

    Devuelve una lista de diccionarios ``{"kind": "line"|"point", "name", "color",
    "points": [[lat, lon], ...]}``. Una MultiGeometry con varias líneas da una entrada
    por línea («nombre (2)», …).
    """
    if not data:
        raise KmlError("El archivo está vacío.")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False,
                             recover=False)
    try:
        root = etree.fromstring(_kml_bytes(data), parser=parser)
    except etree.XMLSyntaxError as error:
        raise KmlError("El archivo no es un KML válido: %s" % error) from error
    colors = _styles(root)
    items = []
    for placemark in root.iter():
        if _local(placemark.tag) != "Placemark":
            continue
        name = _text(placemark, "name")
        color = None
        inline = _children(placemark, "Style")
        if inline:
            line_style = _find(inline[0], "LineStyle")
            if line_style is not None:
                color = kml_color_to_hex(_text(line_style, "color"))
        if not color:
            color = colors.get(_text(placemark, "styleUrl").lstrip("#"))
        lines = [e for e in placemark.iter() if _local(e.tag) == "LineString"]
        for index, line in enumerate(lines, start=1):
            points = _coordinates(_text(line, "coordinates"))
            if len(points) < 2:
                continue
            label = name if len(lines) == 1 else "%s (%s)" % (name, index)
            items.append({"kind": "line", "name": label, "color": color, "points": points})
        for point in (e for e in placemark.iter() if _local(e.tag) == "Point"):
            points = _coordinates(_text(point, "coordinates"))
            if points:
                items.append({"kind": "point", "name": name, "color": None,
                              "points": points[:1]})
    return items
