"""Correcciones deducidas al cruzar el CSV de NAP con el de tramos.

Reglas generales, sin arreglos fila por fila. Cada corrección se devuelve para el
registro de la importación; nada se cambia en silencio. Las sospechas no cambian datos:
se devuelven como marcas «revisar en campo».

Las NAP son diccionarios con ``code``, ``name``, ``branch_line``, ``pon_port``,
``latitude`` y ``longitude``. Los tramos, con ``code``, ``name``, ``segment_type``,
``length_m``, ``nap_codes`` (en orden), ``start_latitude``, ``start_longitude``,
``end_latitude`` y ``end_longitude``.
"""
import re
import unicodedata

from .geo import haversine, path_length

#: Palabras que el relevamiento escribe sin ñ ni tilde. Ampliable.
ACCENT_FIXES = {
    "espana": "España",
}
#: Palabras que no cuentan al comparar nombres de ramal («F.O de 24 H.» = «F.O 24 H»).
STOPWORDS = {"de", "del", "la", "las", "el", "los"}

#: Distancia a la NAP más cercana de su serie a partir de la que se sospecha la ubicación.
SERIES_DISTANCE_M = 1000.0
#: Distancia entre el inicio de un tramo y su primera NAP que merece aviso.
START_DISTANCE_M = 100.0
#: Tolerancia al comparar largos.
LENGTH_TOLERANCE = 0.10

#: Colores de tramo cuando el tramo no trae uno. Un solo lugar para toda la paleta.
#: Por tipo: el troncal y el alimentador tienen color propio, que no usa ningún ramal.
TYPE_COLORS = {
    "troncal": "#f57c00",      # naranja fuerte
    "alimentador": "#8e24aa",  # violeta
}
#: Pistas del mapa de referencia en Google Earth, por clave de ramal (:func:`compact_key`):
#: familia H en verdes, ruta I y línea B en rojos distintos, el ramal 4I-15I-16I en azul.
RAMAL_COLORS = {
    "rutahoeste": "#2e7d32",   # verde oscuro
    "rutahsur": "#66bb6a",     # verde medio
    "6iz": "#00e676",          # verde brillante
    "6izext": "#69f0ae",       # verde menta
    "6de": "#9ccc65",          # verde oliva claro
    "6deext": "#aeea00",       # verde lima
    "rutai": "#c62828",        # rojo oscuro
    "lineab": "#ff5252",       # rojo claro
    "rutairamal": "#2962ff",   # azul
}
#: Paleta para los demás ramales, en orden alfabético de ramal. Colores que contrastan
#: con la imagen satelital: sin casi negros ni casi blancos, y sin los tonos de arriba.
PALETTE = [
    "#00e5ff",  # cian
    "#ffd600",  # amarillo
    "#ff4081",  # rosa
    "#00bfa5",  # verde azulado
    "#e040fb",  # magenta
    "#ffab00",  # ámbar
    "#536dfe",  # índigo
    "#c6ff00",  # lima
    "#a1887f",  # marrón claro
    "#4dd0e1",  # aguamarina
    "#0091ea",  # celeste
    "#b388ff",  # lavanda
    "#fbc02d",  # dorado
    "#ff9e80",  # salmón
    "#f48fb1",  # rosa claro
    "#8d6e63",  # marrón
]

_NAME_LENGTH = re.compile(r"\((\d+(?:[.,]\d+)?)\s*m?\)", re.IGNORECASE)


def _strip_accents(text):
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c))


def compact_key(text):
    """Clave para comparar ramales: sin mayúsculas, acentos, signos ni palabras vacías."""
    words = re.findall(r"[a-z0-9]+", _strip_accents(text).lower())
    return "".join(w for w in words if w not in STOPWORDS)


def _accent_count(text):
    return sum(1 for c in text or "" if ord(c) > 127)


def _match_case(word, replacement):
    if word.isupper():
        return replacement.upper()
    if word[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement.lower()


def fix_accents(text):
    """Corrige las palabras de :data:`ACCENT_FIXES` respetando mayúsculas."""
    if not text or not ACCENT_FIXES:
        return text
    pattern = re.compile(r"\b(%s)\b" % "|".join(map(re.escape, ACCENT_FIXES)), re.IGNORECASE)
    return pattern.sub(lambda m: _match_case(m.group(0), ACCENT_FIXES[m.group(0).lower()]),
                       text)


def segment_label(name):
    """Rótulo del ramal en el nombre del tramo: lo que va antes de «:» o de « - »."""
    name = (name or "").strip()
    if ":" in name:
        return name.split(":", 1)[0].strip()
    return name.split(" - ", 1)[0].strip()


def series_of(code):
    """Serie de una NAP por su código: «YAP-H2-01» → «H2»; «YAP-K-06-B» → «K»."""
    parts = (code or "").split("-")
    return parts[1] if len(parts) >= 3 else ""


def name_length(name):
    """Largo en metros escrito en el nombre del tramo («(480M)», «(1180)»), o ``None``."""
    found = _NAME_LENGTH.search(name or "")
    return float(found.group(1).replace(",", ".")) if found else None


class Deduction:
    """Resultado: correcciones aplicadas, avisos y marcas «revisar en campo»."""

    def __init__(self):
        self.corrections = []  # (código, campo, antes, después, motivo)
        self.warnings = []     # (código, texto)
        self.flags = {}        # código → [textos]

    def correct(self, record, field, value, reason):
        before = record.get(field) or ""
        if before == value:
            return
        record[field] = value
        self.corrections.append((record.get("code"), field, before, value, reason))

    def flag(self, code, text):
        self.flags.setdefault(code, []).append(text)

    def lines(self):
        """Textos para el registro de la importación."""
        out = ["%s: deducido: %s «%s» → «%s» (%s)" % c for c in self.corrections]
        out += ["%s: %s" % w for w in self.warnings]
        out += ["%s: revisar en campo: %s" % (code, text)
                for code, texts in sorted(self.flags.items()) for text in texts]
        return out


def deduce(naps, segments):
    """Aplica las reglas sobre las listas (las modifica) y devuelve un :class:`Deduction`."""
    result = Deduction()
    _fix_segment_names(segments, result)
    _deduce_branch_lines(naps, segments, result)
    _deduce_pon_ports(naps, result)
    _assign_colors(segments, result)
    _flag_naps(naps, segments, result)
    _flag_segments(naps, segments, result)
    return result


def _fix_segment_names(segments, result):
    for segment in segments:
        fixed = fix_accents(segment.get("name") or "")
        if fixed != (segment.get("name") or ""):
            result.correct(segment, "name", fixed, "palabra sin tilde o ñ")


def _deduce_branch_lines(naps, segments, result):
    # Rótulo canónico por clave, tomado de los tramos.
    canonical = {}
    for segment in segments:
        label = segment_label(segment.get("name"))
        if label:
            canonical.setdefault(compact_key(label), label)
    # Si la NAP lo escribe con tildes que el tramo no tiene, vale la escritura de la NAP.
    for nap in naps:
        value = (nap.get("branch_line") or "").strip()
        key = compact_key(value)
        if key in canonical and _accent_count(value) > _accent_count(canonical[key]):
            canonical[key] = value
    # Ramales de NAP que no figuran en ningún tramo: se unifica en la escritura más usada.
    spellings = {}
    for nap in naps:
        value = (nap.get("branch_line") or "").strip()
        if value and compact_key(value) not in canonical:
            spellings.setdefault(compact_key(value), []).append(value)
    for key, values in spellings.items():
        canonical[key] = max(set(values), key=lambda v: (values.count(v), _accent_count(v)))

    # 1) Unificar la escritura de los ramales cargados.
    for nap in naps:
        value = (nap.get("branch_line") or "").strip()
        if value and canonical.get(compact_key(value), value) != value:
            result.correct(nap, "branch_line", canonical[compact_key(value)],
                           "misma ruta escrita de otra forma")

    # 2) Completar los vacíos con el ramal del tramo que contiene la NAP.
    containing = {}
    for segment in segments:
        label = segment_label(segment.get("name"))
        if not label:
            continue
        label = canonical.get(compact_key(label), label)
        segment["branch_line"] = label
        for code in segment.get("nap_codes") or []:
            containing.setdefault(code, []).append((segment, label))
    # Un tramo que arranca en una NAP que otro tramo recorre (sin empezar en ella) es
    # una derivación de ese otro tramo.
    def first(segment):
        codes = segment.get("nap_codes") or []
        return codes[0] if codes else None

    parents = {}
    for segment in segments:
        start = first(segment)
        parents[id(segment)] = {id(other) for other in segments if other is not segment
                                and start in (other.get("nap_codes") or [])
                                and first(other) != start}
    for nap in naps:
        if (nap.get("branch_line") or "").strip():
            continue
        code = nap.get("code")
        found = containing.get(code, [])
        if not found:
            continue
        branches = [(seg, label) for seg, label in found if seg.get("segment_type") != "troncal"]
        trunk = {label for seg, label in found if seg.get("segment_type") == "troncal"}
        # La NAP donde arranca un ramal pertenece a la ruta de la que se deriva.
        inner = [(seg, label) for seg, label in branches if first(seg) != code]
        candidate_ids = {id(seg) for seg, label in inner}
        inner = [(seg, label) for seg, label in inner
                 if not parents[id(seg)] & candidate_ids]
        labels = {label for seg, label in inner}
        if len(labels) == 1:
            result.correct(nap, "branch_line", labels.pop(),
                           "tramo %s que contiene la NAP" % inner[0][0].get("code"))
        elif len(labels) > 1:
            result.warnings.append((code, "ramal ambiguo, figura en tramos de %s; queda vacío"
                                    % ", ".join(sorted(labels))))
        elif len(trunk) == 1:
            reason = ("inicio de ramal sobre el troncal" if branches
                      else "solo figura en el troncal")
            result.correct(nap, "branch_line", trunk.pop(), reason)
        elif len({label for seg, label in branches}) == 1:
            result.correct(nap, "branch_line", branches[0][1],
                           "inicio del tramo %s" % branches[0][0].get("code"))
        elif branches:
            result.warnings.append((code, "ramal ambiguo, inicio de los tramos de %s; queda "
                                    "vacío" % ", ".join(sorted({l for s, l in branches}))))


def _deduce_pon_ports(naps, result):
    groups = {}
    for nap in naps:
        key = (series_of(nap.get("code")), compact_key(nap.get("branch_line")))
        if key[0] and key[1]:
            groups.setdefault(key, []).append(nap)
    for (series, _branch), members in groups.items():
        values = {(n.get("pon_port") or "").strip() for n in members} - {""}
        if len(values) != 1:
            continue
        value = values.pop()
        for nap in members:
            if not (nap.get("pon_port") or "").strip():
                result.correct(nap, "pon_port", value,
                               "único puerto PON de la serie %s en el mismo ramal" % series)


def ramal_colors(labels):
    """Color de cada ramal (sin tipo especial): pista de :data:`RAMAL_COLORS` o paleta.

    Determinista: los ramales sin pista toman la paleta en orden alfabético de clave.
    """
    keys = sorted({compact_key(label) for label in labels if label})
    colors = {}
    free = [k for k in keys if k not in RAMAL_COLORS]
    for key in keys:
        if key in RAMAL_COLORS:
            colors[key] = RAMAL_COLORS[key]
        else:
            colors[key] = PALETTE[free.index(key) % len(PALETTE)]
    return colors


def _assign_colors(segments, result):
    labels = [s.get("branch_line") or segment_label(s.get("name")) for s in segments
              if s.get("segment_type") not in TYPE_COLORS]
    colors = ramal_colors(labels)
    for segment in segments:
        if (segment.get("color") or "").strip():
            continue
        kind = segment.get("segment_type")
        label = segment.get("branch_line") or segment_label(segment.get("name"))
        if kind in TYPE_COLORS:
            color, reason = TYPE_COLORS[kind], "color del tipo %s" % kind
        elif label:
            color, reason = colors[compact_key(label)], "color del ramal %s" % label
        else:
            continue
        result.correct(segment, "color", color, reason)


def _has_point(record, lat="latitude", lon="longitude"):
    return record.get(lat) is not None and record.get(lon) is not None


def _flag_naps(naps, segments, result):
    in_segment = {code for s in segments for code in s.get("nap_codes") or []}
    by_series = {}
    for nap in naps:
        if series_of(nap.get("code")) and _has_point(nap):
            by_series.setdefault(series_of(nap.get("code")), []).append(nap)
    for nap in naps:
        code = nap.get("code")
        if segments and code not in in_segment:
            result.flag(code, "no figura en ningún tramo")
        others = [n for n in by_series.get(series_of(code), []) if n is not nap]
        if _has_point(nap) and others:
            nearest = min(others, key=lambda n: haversine(
                nap["latitude"], nap["longitude"], n["latitude"], n["longitude"]))
            distance = haversine(nap["latitude"], nap["longitude"],
                                 nearest["latitude"], nearest["longitude"])
            if distance > SERIES_DISTANCE_M:
                result.flag(code, "ubicación probablemente errónea: la NAP más cercana de "
                                  "su serie (%s) está a %.0f m" % (nearest.get("code"), distance))


def _flag_segments(naps, segments, result):
    points = {n.get("code"): (n["latitude"], n["longitude"]) for n in naps if _has_point(n)}
    for segment in segments:
        code = segment.get("code")
        length = segment.get("length_m") or 0.0
        written = name_length(segment.get("name"))
        if written and length and abs(written - length) / written > LENGTH_TOLERANCE:
            result.flag(code, "el nombre dice %.0f m y longitud_m es %.1f m" % (written, length))
        route = [points[c] for c in segment.get("nap_codes") or [] if c in points]
        start = end = None
        if _has_point(segment, "start_latitude", "start_longitude"):
            start = (segment["start_latitude"], segment["start_longitude"])
        if _has_point(segment, "end_latitude", "end_longitude"):
            end = (segment["end_latitude"], segment["end_longitude"])
        path = ([start] if start else []) + route + ([end] if end else [])
        minimum = path_length(path)
        if length and minimum > length * (1 + LENGTH_TOLERANCE):
            result.flag(code, "longitud_m (%.1f m) es menor que el recorrido mínimo inicio → "
                              "NAP → fin (%.0f m)" % (length, minimum))
        if start and route:
            distance = haversine(start[0], start[1], route[0][0], route[0][1])
            if distance > START_DISTANCE_M:
                result.flag(code, "el inicio está a %.0f m de su primera NAP (informativo)"
                            % distance)
