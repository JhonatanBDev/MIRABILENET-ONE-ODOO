"""Especificaciones que se leen del nombre de un producto DigiCorp
('CAMARA IP DOMO 4MP *LENTE 2.8MM *PoE ...'). Traído de referencia/digicorp/parsers.py."""
import re


def clean(s):
    if s is None:
        return None
    s = " ".join(str(s).split())
    return s or None


_TIPOS = {
    "PTZ": ["PTZ", "SPEED ?DOME"],
    "PT": ["PT", "PAN ?TILT"],
    "FISHEYE": ["FISHEYE", "OJO DE PEZ", "PANORAMICA"],
    "TURRET": ["TURRET", "TORRETA"],
    "EYEBALL": ["EYEBALL"],
    "DOMO": ["DOMO", "DOME", "MINIDOMO"],
    "BULLET": ["BULLET", "BALA", "TUBO", "TUBULAR"],
    "PINHOLE": ["PINHOLE"],
    "CUBO": ["CUBO", "CUBE"],
}


def parse_specs(texto):
    """Extrae specs útiles del nombre/descripcion ('CAMARA IP DOMO 4MP *LENTE 2.8MM *PoE ...')."""
    t = clean(texto) or ""
    up = t.upper()
    partes = [clean(p) for p in t.split("*")]
    specs = {"titulo": partes[0] if partes else None,
                             "caracteristicas": [p for p in partes[1:] if p]}
    mps = [float(x.replace(",", ".")) for x in re.findall(r"(\d+(?:[.,]\d+)?)\s*MP\b", up)]
    if mps:
        specs["resolucion_mp"] = max(mps)
    elif "4K" in up:
        specs["resolucion_mp"] = 8.0
    if m := re.search(r"LENTE[^*]*?(\d+(?:[.,]\d+)?)\s*MM", up):
        specs["lente_mm"] = float(m.group(1).replace(",", "."))
    if m := re.search(r"(?:ILUM|IR|INFRARROJ|DISTANCIA)[^*]{0,25}?(\d+)\s*M\b", up):
        specs["alcance_ir_m"] = int(m.group(1))
    if m := re.search(r"\bIP\s?(6[5-8])\b", up):
        specs["ip_rating"] = f"IP{m.group(1)}"
    if m := re.search(r"(\d+)\s*(?:CH|CANALES)\b", up):
        specs["canales"] = int(m.group(1))
    if m := re.search(r"(\d+)\s*(?:PUERTOS|PTOS)", up):
        specs["puertos"] = int(m.group(1))
    for rx in (r"(\d+)\s*PUERTOS?\s*(?:DE\s*)?POE", r"(\d+)\s*(?:X\s*)?POE\b", r"POE\s*DE\s*(\d+)\s*PUERTOS"):
        if m := re.search(rx, up):
            specs["poe_puertos"] = int(m.group(1))
            break
    # potencia total; se ignora "30W POR PUERTO"
    if m := re.search(r"(\d+(?:[.,]\d+)?)\s*W\b(?!\s*(?:POR|X)\s*PUERTO)", up):
        specs["potencia_w"] = float(m.group(1).replace(",", "."))
    if m := re.search(r"(\d+)\s*HDD", up):
        specs["hdd_bahias"] = int(m.group(1))
    if m := re.search(r"HDD\s*(?:DE\s*)?HASTA\s*(\d+)\s*TB", up):
        specs["hdd_max_tb"] = int(m.group(1))
    if m := re.search(r"(\d+(?:[.,]\d+)?)\s*TB\b", up):
        specs["capacidad_tb"] = float(m.group(1).replace(",", "."))
    specs["poe"] = bool(re.search(r"\bPOE\b", up))
    specs["wifi"] = bool(re.search(r"WI-?FI|INALAMBRIC", up))
    specs["audio"] = bool(re.search(r"AUDIO|MIC", up))
    specs["exterior"] = bool(re.search(r"IP6[5-8]|EXTERIOR|OUTDOOR", up))
    specs["full_color"] = bool(re.search(r"FULL ?COLOR|WIZCOLOR|COLORVU|SMART DUAL", up))
    for tipo, sinonimos in _TIPOS.items():
        if re.search(rf"\b(?:{'|'.join(sinonimos)})\b", up):
            specs["tipo"] = tipo
            break
    return specs
