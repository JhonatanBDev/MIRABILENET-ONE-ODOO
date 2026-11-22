"""Descomposición de los métodos de pago del catálogo del SIN.

El catálogo mezcla medios simples («EFECTIVO», «TARJETA», «GIFT-CARD») con
combinaciones («EFECTIVO - TARJETA»). Aquí se deduce, usando solo los nombres
del propio catálogo sincronizado, qué medios simples componen cada código.

No hay lista fija de medios: si un nombre no se puede interpretar con
seguridad, no se adivina (devuelve None).
"""

import re

_DASHES = re.compile(r"[‐-―−]")
_STOPWORDS = {"DE", "EN", "EL", "LA", "Y"}


def normalize(name):
    """Mayúsculas, guiones unificados, sin espacios alrededor del guion y sin
    palabras vacías: «Canal  de Pago» y «CANAL PAGO» resultan iguales."""
    text = _DASHES.sub("-", (name or "").upper())
    parts = []
    for part in text.split("-"):
        words = [w for w in part.split() if w not in _STOPWORDS]
        parts.append(" ".join(words))
    return "-".join(p for p in parts if p)


def _resolve(group, simples):
    """Nombre simple que corresponde a un fragmento: coincidencia exacta o
    prefijo que identifica a un único medio simple."""
    if group in simples:
        return group
    candidates = [s for s in simples if s.startswith(group + "-") or s.startswith(group + " ")]
    return candidates[0] if len(candidates) == 1 else None


def _segment(parts, simples):
    """Parte la lista de fragmentos en grupos consecutivos que sean medios
    simples conocidos. Devuelve la lista de medios o None."""
    if not parts:
        return []
    for size in range(len(parts), 0, -1):
        head = _resolve("-".join(parts[:size]), simples)
        if head is None:
            continue
        tail = _segment(parts[size:], simples)
        if tail is not None:
            return [head] + tail
    return None


def decompose(names):
    """names: {clave: nombre del catálogo}. Devuelve {clave: [medios]|None}.

    Un nombre es «simple» si no puede partirse en dos o más nombres del
    catálogo. Las combinaciones se expresan con esos medios simples.
    """
    normalized = {key: normalize(name) for key, name in names.items()}
    known = set(normalized.values())
    simples = set()
    for value in known:
        parts = value.split("-")
        composite = False
        if len(parts) > 1:
            others = known - {value}
            for cut in range(1, len(parts)):
                if "-".join(parts[:cut]) in others and _segment(parts[cut:], others) is not None:
                    composite = True
                    break
        if not composite:
            simples.add(value)
    result = {}
    for key, value in normalized.items():
        if value in simples:
            # Un simple con guion ("A-B") cuyos fragmentos se resuelven por
            # prefijo a otros simples es en realidad una combinación.
            parts = value.split("-")
            alt = _segment(parts, simples - {value}) if len(parts) > 1 else None
            result[key] = sorted(set(alt)) if alt and len(alt) > 1 else [value]
        else:
            segments = _segment(value.split("-"), simples)
            result[key] = sorted(set(segments)) if segments else None
    return result


def components_key(components):
    """Clave estable e independiente del orden para comparar combinaciones."""
    return "|".join(sorted(set(components))) if components else False
