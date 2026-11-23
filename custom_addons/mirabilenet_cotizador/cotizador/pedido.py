"""Lectura por REGLAS de un pedido en texto libre (sin IA). Traída de referencia/core/pedido.py.

Extrae solo lo que está escrito de forma explícita: cantidades, interior/exterior, tecnología,
gama, megapíxeles, días, disco pedido ("disco de 500gb", "1 tera") y metros de cable.
Sirve para dos cosas:
  1. corregir a la IA (n8n), que a veces inventa grupos, días o títulos;
  2. armar el pedido cuando no hay IA.
Lo que no aparece en el texto queda en None: nunca se inventa.
"""
import re
import unicodedata
from dataclasses import dataclass, field

_NUMEROS = {"dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
            "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "dieciseis": 16, "veinte": 20,
            "treinta": 30}
_INTERIOR = r"adentro|dentro|interior(?:es)?|internas?|sala|oficinas?|pasillos?|cocina|dormitorios?|mostrador|caja"
_EXTERIOR = (r"afuera|fuera|exterior(?:es)?|externas?|patios?|calle|puertas?|fachada|garajes?|entrada|jardin|"
             r"parqueos?|porton|terraza|intemperie|muro|perimetros?")
_LUGARES = (r"casa|tienda|oficina|galpon|colegio|bodega|almacen|deposito|restaurante|farmacia|departamento|"
            r"edificio|taller|local|hotel|condominio|consultorio|clinica|fabrica|ferreteria|licoreria|"
            r"minimarket|supermercado|escuela|iglesia|gimnasio|cafeteria|panaderia|quinta|terreno|granja")
_PALABRAS =r"(?:[^\W\d]+\s+){0,4}?"          # hasta 4 palabras sin números entre la cantidad y el lugar


@dataclass
class Pistas:
    total: int = None            # "4 cámaras"
    interior: int = None
    exterior: int = None
    solo_exterior: bool = False         # menciona exterior sin cantidad ("4 cámaras para exterior")
    tecnologia: str = None       # ip | analogica
    economica: bool = False
    mp: float = None
    dias: int = None
    disco_gb: float = None       # disco pedido de forma explícita
    metros: float = None
    movimiento: bool = False            # grabación por detección de movimiento
    tipos: list = field(default_factory=list)
    numeros: set = field(default_factory=set)   # todos los números del texto (para validar a la IA)
    lugar: str = ""                     # "tienda de ropa", "casa", "galpon"...


def limpiar(texto: str) -> str:
    """minúsculas, sin tildes, números en palabras -> dígitos."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"\b(" + "|".join(_NUMEROS) + r")\b", lambda m: str(_NUMEROS[m.group(1)]), t)


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def analizar(texto: str) -> Pistas:
    t = limpiar(texto)
    p = Pistas(numeros=set(re.findall(r"\d+", t)))
    if m := re.search(rf"\b(?:{_LUGARES})(?:\s+de\s+[a-z]{{3,}})?\b", t):
        p.lugar = m.group(0)

    # ---- disco pedido (se quita del texto para que "500" no se confunda con otra cosa)
    if m := re.search(r"(\d+(?:[.,]\d+)?)\s*(?:tb|teras?|terabytes?)\b", t):
        p.disco_gb = _num(m.group(1)) * 1000
    elif m := re.search(r"(\d+)\s*(?:gb|gigas?|gigabytes?)\b", t):
        if _num(m.group(1)) >= 100:                      # 64 GB sería una micro SD, no un disco
            p.disco_gb = _num(m.group(1))
    if m:
        t = t[:m.start()] + " " + t[m.end():]

    # ---- días de grabación
    if m := re.search(r"(\d+)\s*dias?\b", t):
        p.dias = int(m.group(1))
    elif m := re.search(r"(\d+)\s*semanas?\b", t):
        p.dias = int(m.group(1)) * 7
    elif m := re.search(r"(\d+)\s*mes(?:es)?\b", t):
        p.dias = int(m.group(1)) * 30
    elif m := re.search(r"\bun mes\b", t):
        p.dias = 30
    elif m := re.search(r"\buna semana\b", t):
        p.dias = 7
    if m:
        t = t[:m.start()] + " " + t[m.end():]

    # ---- metros de cable
    if m := re.search(r"(\d+(?:[.,]\d+)?)\s*(?:mts?|metros?)\b", t):
        p.metros = _num(m.group(1))
        t = t[:m.start()] + " " + t[m.end():]

    # ---- resolución
    if m := re.search(r"(\d+(?:[.,]\d+)?)\s*(?:mp|megas?|megapixel(?:es)?)\b", t):
        p.mp = _num(m.group(1))
        t = t[:m.start()] + " " + t[m.end():]
    elif re.search(r"\b4k\b|ultra ?hd", t):
        p.mp = 8
    elif re.search(r"\b2k\b", t):
        p.mp = 4
    elif re.search(r"full ?hd|\b1080p?\b", t):
        p.mp = 2
    t = re.sub(r"\b(?:4k|2k|1080p?|720p?)\b", " ", t)

    # ---- tecnología y gama
    if re.search(r"analogic|hdcvi|\bcvi\b|\bahd\b|\btvi\b|coaxial|\bdvr\b|\bxvr\b", t):
        p.tecnologia = "analogica"
    elif re.search(r"\bip\b|\bnvr\b|\bpoe\b", t):
        p.tecnologia = "ip"
    p.economica = bool(re.search(r"economic|barat|basic|ajustad|low ?cost|menor precio|mas bajo|accesible", t))
    p.movimiento = bool(re.search(r"movimiento|deteccion", t))
    for tipo, rx in (("DOMO", r"\bdomos?\b"), ("BULLET", r"\bbalas?\b|\bbullets?\b|\btubos?\b"),
                     ("PTZ", r"\bptz\b"), ("PT", r"\bpt\b|que gir|giratori")):
        if re.search(rx, t):
            p.tipos.append(tipo)

    # ---- cantidades por ubicación
    def cuenta(lugares: str) -> int:
        ms = re.findall(rf"(\d+)\s+(?:camaras?\s+)?{_PALABRAS}(?:{lugares})\b", t)
        return sum(int(x) for x in ms) if ms else None

    p.interior, p.exterior = cuenta(_INTERIOR), cuenta(_EXTERIOR)
    tot = re.findall(r"(\d+)\s*(?:camaras?|cam\b|cams\b|puntos?\b)", t)
    if not tot:
        tot = re.findall(r"(?:kit|sistema|cctv)\s+(?:de\s+)?(\d+)\b", t)
    if tot:
        p.total = sum(int(x) for x in tot)
    partes = (p.interior or 0) + (p.exterior or 0)
    if partes and (p.total is None or p.total < partes):
        p.total = partes
    if p.total and partes and p.total > partes:          # "8 cámaras, 2 afuera" -> 6 adentro
        if p.interior is None:
            p.interior = p.total - partes
        elif p.exterior is None:
            p.exterior = p.total - partes
    p.solo_exterior = (p.exterior is None and p.interior is None
                       and bool(re.search(rf"\b(?:{_EXTERIOR})\b", t)) and not re.search(rf"\b(?:{_INTERIOR})\b", t))
    return p


def etiqueta_disco(gb: float) -> str:
    """500 -> '500 GB' | 1000 -> '1 TB' | 2000 -> '2 TB'"""
    return f"{gb / 1000:g} TB" if gb >= 1000 else f"{gb:g} GB"
