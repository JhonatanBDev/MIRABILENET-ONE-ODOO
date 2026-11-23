"""Selección automática de SKUs según requisitos, con stock en la ciudad.
Traída de referencia/core/selector.py: en vez de SQLAlchemy recibe un catálogo `cat`
(lo arma Odoo) con `productos(categorias)` y `por_sku(sku)`.


Regla general:
1. Filtrar por categoría DigiCorp + patrón en el nombre (DigiCorp repite productos en
   hojas ajenas, p.ej. cámaras dentro de "GRABADORES IP 8CH").
2. Filtrar por requisitos técnicos (specs extraídas del nombre/descripcion).
3. Exigir stock en almacenes de la ciudad (showroom no cuenta). Si nadie cumple, se elige
   el mejor sin stock y se emite alerta.
4. Puntuar costo/beneficio; bonus a marcas con repuestos locales.
"""
import math
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

from .specs import parse_specs

CATS_CAMARA = ["CAMARAS IP"]
CATS_NVR = ["GRABADORES IP"]
# Analógico (HDCVI/AHD/TVI). DigiCorp lista algunas cámaras HAC dentro de GRABADORES ANALOGICOS:
# se filtran por nombre (CAMARA vs GRABADOR/XVR/DVR).
CATS_CAMARA_ANALOG = ["CAMARAS ANALOGICAS", "GRABADORES ANALOGICOS"]
CATS_DVR = ["GRABADORES ANALOGICOS"]
GAMAS = ("estandar", "economica")
CATS_DISCO = ["DISCOS DUROS Y SERVIDORES", "ALMACENAMIENTO"]
CATS_SWITCH = ["REDES CCTV", "TPLINK", "MERCUSYS", "UBIQUITI", "MIKROTIK", "TRENDNET", "BDCOM"]
DISCO_VIGILANCIA = re.compile(r"PURPLE|SKYHAWK|VIGILANCIA|SURVEILLANCE|VIDEOVIG", re.I)


@dataclass
class Candidato:
    p: object
    specs: dict
    stock: int          # None = falta la ficha: stock por ciudad sin verificar
    score: float = 0.0
    motivo: str = ""

    @property
    def costo(self):
        return Decimal(self.p.costo)


@dataclass
class Eleccion:
    cand: Candidato
    cantidad: int = 1
    alertas: list = field(default_factory=list)


def specs_de(p):
    return parse_specs(f"{p.nombre} *{p.descripcion or ''}")


def _sin_tildes(t: str):
    """'CÁMARA' -> 'CAMARA' (los patrones de config se escriben sin tildes)."""
    return "".join(c for c in unicodedata.normalize("NFKD", t or "") if not unicodedata.combining(c))


def candidatos(cat, categorias, patron, ciudad, excluir=None):
    """Productos activos de esas categorías cuyo nombre cumple el patrón, con su stock en la
    ciudad (None = sin verificar)."""
    rx, rx_ex = re.compile(patron, re.I), re.compile(excluir, re.I) if excluir else None
    prods = [p for p in cat.productos(categorias) if p.costo and p.costo > 0
             and rx.search(_sin_tildes(p.nombre))
             and not (rx_ex and rx_ex.search(_sin_tildes(p.nombre)))]
    return [Candidato(p, specs_de(p), p.stock_en(ciudad)) for p in prods]


def _st(c: Candidato):
    return c.stock or 0


def alerta_no_verificado(c: Candidato, ciudad: str):
    return (f"Stock en {ciudad} sin verificar (hay {c.p.stock_total} a nivel nacional; falta la ficha): "
            f"actualizar {c.p.sku} desde DigiCorp")


def _brand_bonus(cfg, marca: str):
    prefs = {m.upper() for m in cfg.marcas_preferidas}
    return 1 + cfg.bonus_marca_preferida if (marca or "").upper() in prefs else 1.0


def _elegir(cands, cantidad: int, que: str, ciudad: str):
    if not cands:
        return Eleccion(None, cantidad, [f"No hay {que} en el catálogo que cumpla los requisitos"])
    con_stock = [c for c in cands if _st(c) >= cantidad]
    if con_stock:
        mejor = max(con_stock, key=lambda c: (c.score, _st(c)))
        return Eleccion(mejor, cantidad)
    sin_verificar = [c for c in cands if c.stock is None]
    if sin_verificar:
        mejor = max(sin_verificar, key=lambda c: (c.score, c.p.stock_total))
        return Eleccion(mejor, cantidad, [alerta_no_verificado(mejor, ciudad)])
    mejor = max(cands, key=lambda c: (c.score, _st(c)))
    return Eleccion(mejor, cantidad, [
        f"Sin stock suficiente en {ciudad} ({mejor.stock} de {cantidad}); ningún {que} cumple con stock"])


# ------------------------------------------------------------------ cámaras
def elegir_camara(cat, cfg, req, ciudad: str,
                  tecnologia: str = "ip", gama: str = "estandar"):
    """gama 'economica': la más barata que cumpla los mínimos (sin puntos por extras ni marca)."""
    cantidad = int(req["cantidad"])
    analog = tecnologia == "analogica"
    mp_min = float(req.get("resolucion_min", 2))
    exterior = req.get("ubicacion", "interior") == "exterior"
    tipos = [t.upper() for t in req.get("tipos") or []]
    base = candidatos(cat, CATS_CAMARA_ANALOG if analog else CATS_CAMARA, r"\bC[AÁ]MARA", ciudad,
                      excluir=r"ESPIA|PINHOLE|DEPORTIV|VEHICULAR|BEB[EÉ]")

    def ok(c: Candidato, con_tipo: bool):
        sp = c.specs
        if sp.get("resolucion_mp", 0) < mp_min:
            return False
        if not analog and req.get("poe") and not sp.get("poe"):
            return False
        if not req.get("wifi", False) and sp.get("wifi"):
            return False
        if exterior and not sp.get("exterior"):
            return False
        if sp.get("tipo") in ("PT", "PTZ") and not set(tipos) & {"PT", "PTZ"}:
            return False
        return not (con_tipo and tipos and sp.get("tipo") not in tipos)

    cands = [c for c in base if ok(c, True)]
    relajado = False
    if not [c for c in cands if _st(c) >= cantidad or c.stock is None]:   # tipo correcto > tipo con stock
        alt = [c for c in base if ok(c, False)]
        if [c for c in alt if _st(c) >= cantidad]:
            cands, relajado = alt, True
    for c in cands:
        sp = c.specs
        beneficio = (1 + 0.12 * (sp.get("resolucion_mp", mp_min) - mp_min)
                     + 0.10 * bool(sp.get("full_color")) + 0.05 * bool(sp.get("audio"))
                     + 0.05 * (sp.get("alcance_ir_m", 0) >= 30)
                     + (0.05 if sp.get("tipo") in tipos[:1] else 0))
        if gama == "economica":
            beneficio = 1.0 + 0.02 * bool(sp.get("tipo") in tipos[:1])     # casi solo precio
        bonus = 1.0 if gama == "economica" else _brand_bonus(cfg, c.p.marca)
        c.score = beneficio * bonus / float(c.costo) * 1000
        c.motivo = (f"{sp.get('resolucion_mp', '?')} MP {sp.get('tipo') or ''} "
                    f"{'PoE ' if sp.get('poe') else ''}{'ext ' if sp.get('exterior') else ''}"
                    f"{'full color ' if sp.get('full_color') else ''}| score {c.score:.2f} | stock {c.stock}").strip()
    e = _elegir(cands, cantidad, f"cámara {'analógica ' if analog else ''}{req.get('ubicacion')} ≥{mp_min:g}MP",
                ciudad)
    if relajado and e.cand:
        e.alertas.append(f"Ninguna cámara de tipo {'/'.join(tipos)} con stock: se eligió tipo {e.cand.specs.get('tipo') or 'sin especificar'}")
    return e


# ------------------------------------------------------------------ NVR
def elegir_nvr(cat, cfg, canales: int, mp_max: float, poe_puertos: int,
               ciudad: str, tb_requeridos: float = 0, analogico: bool = False,
               gama: str = "estandar"):
    """NVR (IP) o, con analogico=True, DVR/XVR pentahíbrido."""
    if analogico:
        base = candidatos(cat, CATS_DVR, r"GRABADOR|RABADOR|XVR|DVR", ciudad,
                          excluir=r"C[AÁ]MARA|MOVIL|VEHICULAR")
        poe_puertos = 0
    else:
        base = candidatos(cat, CATS_NVR, r"GRABADOR|NVR", ciudad, excluir=r"MOVIL|VEHICULAR")
    cands = []
    for c in base:
        sp = c.specs
        if analogico and mp_max > 2 and not re.search(r"4K|[5-8] ?MP|5M\b", c.p.nombre.upper()):
            continue                                   # cámaras > 2 MP: XVR que soporte 4K/5MP
        if sp.get("poe") and "poe_puertos" not in sp and sp.get("canales"):
            sp["poe_puertos"] = sp["canales"]          # "NVR POE 8CH": se asume 1 PoE por canal
            sp["poe_supuesto"] = True
        if sp.get("canales", 0) < canales:
            continue
        if poe_puertos and sp.get("poe_puertos", 0) < poe_puertos:
            continue
        if not analogico and sp.get("resolucion_mp") and sp["resolucion_mp"] < mp_max:
            continue
        if tb_requeridos and sp.get("hdd_max_tb") and sp.get("hdd_bahias", 1) * sp["hdd_max_tb"] < tb_requeridos:
            continue
        # el más barato que cumpla; leve penalización por canales de más
        exceso = (sp["canales"] - canales) / max(canales, 1)
        bonus = 1.0 if gama == "economica" else _brand_bonus(cfg, c.p.marca)
        c.score = bonus / float(c.costo) * 1000 / (1 + 0.2 * exceso)
        c.motivo = (f"{sp['canales']}CH, {sp.get('poe_puertos', 0)} PoE, {sp.get('hdd_bahias', '?')} HDD "
                    f"hasta {sp.get('hdd_max_tb', '?')} TB | stock {c.stock}")
        cands.append(c)
    return _elegir(cands, 1, f"{'DVR/XVR' if analogico else 'NVR'} ≥{canales}CH" + (f" con {poe_puertos} PoE" if poe_puertos else "")
                   + (f" y ≥{tb_requeridos:.1f} TB" if tb_requeridos else ""), ciudad)


# ------------------------------------------------------------------ switch PoE
def elegir_switch(cat, cfg, puertos: int, watts: float, ciudad: str):
    base = candidatos(cat, CATS_SWITCH, r"SWITCH|SWICHT", ciudad)
    cands = []
    for c in base:
        sp = c.specs
        if not sp.get("poe") or sp.get("poe_puertos", 0) < puertos:
            continue
        w = sp.get("potencia_w")
        if w is not None and w < watts:
            continue
        c.score = _brand_bonus(cfg, c.p.marca) / float(c.costo) * 1000 * (1.0 if w else 0.8)
        c.motivo = f"{sp.get('poe_puertos')} PoE, {w or '?'} W | stock {c.stock}"
        cands.append(c)
    e = _elegir(cands, 1, f"switch ≥{puertos} PoE / {watts:.0f} W", ciudad)
    if e.cand and e.cand.specs.get("potencia_w") is None:
        e.alertas.append(f"Presupuesto PoE del switch no indicado: verificar ≥ {watts:.0f} W")
    return e


# ------------------------------------------------------------------ discos
_RX_GB = re.compile(r"(\d{3,4})\s*GB\b(?!\s*/\s*S)", re.I)     # "500GB"; no "6GB/s" (interfaz SATA)
_RX_PULL = re.compile(r"\bPULL\b|RE-? ?EMPAQUETADO", re.I)
AVISO_PULL = ("Disco re-empaquetado (PULL): más barato pero usado/recuperado. Avisar al cliente y ofrecer "
              "el disco nuevo como alternativa")


def capacidad_tb(c: Candidato):
    """TB del disco. DigiCorp escribe los discos chicos en GB ('DISCO DURO PULL WD 500GB')."""
    cap = c.specs.get("capacidad_tb")
    if cap:
        return float(cap)
    m = _RX_GB.search(c.p.nombre.split("*")[0]) or _RX_GB.search(c.p.nombre)
    return int(m.group(1)) / 1000 if m else None


def es_pull(c: Candidato):
    return bool(_RX_PULL.search(c.p.nombre))


def etq_tb(tb: float):
    return f"{tb:g} TB" if tb >= 1 else f"{tb * 1000:g} GB"


def elegir_disco_fijo(cat, cfg, tb: float, max_tb_bahia: float,
                      ciudad: str, permitir_pull: bool = False):
    """El cliente pidió un disco concreto (500 GB, 1 TB...). Orden de preferencia:
    1) si aceptó re-empaquetado (PULL): el PULL de esa capacidad con stock (lo más barato);
    2) nuevo de esa capacidad con stock;
    3) PULL de esa capacidad si no hay nuevo (p. ej. 500 GB solo existe en PULL), con alerta;
    4) el disco nuevo más barato de capacidad mayor, con alerta."""
    base = candidatos(cat, CATS_DISCO, r"DISCO|HDD", ciudad, excluir=r"SSD|EXTERNO|PORTATIL|NAS|SERVIDOR")
    iguales = [c for c in base if (cap := capacidad_tb(c)) and abs(cap - tb) < 0.01]
    nuevos = [c for c in iguales if not es_pull(c)]
    pulls = [c for c in iguales if es_pull(c)]

    def mejor(cs):
        ok = [c for c in cs if _st(c) >= 1]
        return min(ok, key=lambda c: (c.costo * (Decimal("0.9") if DISCO_VIGILANCIA.search(c.p.nombre) else 1),
                                      -_st(c))) if ok else None

    def listo(c: Candidato, alertas):
        c.specs["capacidad_tb"] = capacidad_tb(c)
        c.motivo = (f"1 × {etq_tb(c.specs['capacidad_tb'])} (pedido por el cliente)"
                    f"{' videovigilancia' if DISCO_VIGILANCIA.search(c.p.nombre) else ''}"
                    f"{' re-empaquetado' if es_pull(c) else ''} | stock {c.stock}")
        return Eleccion(c, 1, alertas)

    if permitir_pull and (c := mejor(pulls)):
        return listo(c, [AVISO_PULL])
    if c := mejor(nuevos):
        return listo(c, [])
    if c := mejor(pulls):
        porque = "no existe disco nuevo de esa capacidad" if not nuevos else f"el nuevo no tiene stock en {ciudad}"
        return listo(c, [f"{AVISO_PULL} ({porque})"])
    e = elegir_discos(cat, cfg, tb, 1, max_tb_bahia, ciudad)         # la capacidad siguiente
    if e.cand:
        e.alertas.insert(0, f"No hay disco de {etq_tb(tb)} con stock en {ciudad}: se cotizó el de "
                            f"{etq_tb(e.cand.specs.get('capacidad_tb') or 0)}")
        return e
    return Eleccion(None, 0, [f"No hay disco de {etq_tb(tb)} ni mayor con stock en {ciudad}"])


def elegir_discos(cat, cfg, tb: float, bahias: int, max_tb_bahia: float,
                  ciudad: str, permitir_pull: bool = False):
    # PULL = disco usado/recuperado: no va en kits para clientes salvo que se acepte de forma explícita
    base = candidatos(cat, CATS_DISCO, r"DISCO|HDD", ciudad, excluir=r"SSD|EXTERNO|PORTATIL|NAS|SERVIDOR")
    if not permitir_pull:
        base = [c for c in base if not es_pull(c)]
    mejor = None
    sin_stock = None
    for c in base:
        cap = capacidad_tb(c)
        c.specs["capacidad_tb"] = cap
        if not cap or (max_tb_bahia and cap > max_tb_bahia):
            continue
        n = max(1, math.ceil(tb / cap))
        if n > bahias:
            continue
        costo = c.costo * n * (Decimal("0.9") if DISCO_VIGILANCIA.search(c.p.nombre) else 1)
        c.motivo = (f"{n} × {cap:g} TB = {n * cap:g} TB (≥ {tb:.2f}){' videovigilancia' if DISCO_VIGILANCIA.search(c.p.nombre) else ''}"
                    f"{' re-empaquetado' if es_pull(c) else ''}"
                    f" | stock {c.stock}")
        key = (costo, n, c)
        if _st(c) >= n:
            if mejor is None or key[:2] < mejor[:2]:
                mejor = key
        else:                    # sin stock en la ciudad: primero los que hay en otras ciudades
            k2 = (c.p.stock_total < n, costo, n, c)
            if sin_stock is None or k2[:3] < sin_stock[:3]:
                sin_stock = k2
    if mejor:
        return Eleccion(mejor[2], mejor[1], [AVISO_PULL] if es_pull(mejor[2]) else [])
    if sin_stock:
        c, n = sin_stock[3], sin_stock[2]
        if c.stock is None:
            msg = alerta_no_verificado(c, ciudad)
        elif c.p.stock_total >= n:
            msg = (f"Sin disco adecuado con stock en {ciudad}: {c.p.sku} tiene {c.p.stock_total} en otras "
                   f"ciudades (traslado) o reducir días de grabación")
        else:
            msg = f"Sin stock de disco adecuado en ninguna ciudad"
        return Eleccion(c, n, [msg])
    return Eleccion(None, 0, [f"Ningún disco cubre {tb:.2f} TB con {bahias} bahía(s)"
                              + (f" de máx. {max_tb_bahia} TB" if max_tb_bahia else "")])


# ------------------------------------------------------------------ materiales
@dataclass
class Material:
    clave: str
    descripcion: str
    unidad: str
    costo_unit: Decimal
    sku: str
    categoria: str
    stock: int
    alertas: list = field(default_factory=list)
    precio_item: Decimal = None      # precio DigiCorp del ítem completo (escalón de recargo)


def unidades_por_item(nombre: str, unidad: str, defecto: Decimal):
    """Unidades (o metros) que trae un ítem DigiCorp, leído del nombre.
    '305 METROS' -> 305 | 'PAQUETE DE 10 UNIDADES ... LONGITUD DE 2 MTS' -> 20 m | 'BOLSA DE 10 UNIDADES' -> 10."""
    up = nombre.upper()
    paquete = re.search(r"(?:BOLSA|PAQUETE|CAJA|PACK)\s*(?:DE\s*)?(\d+)\s*(?:UNIDADES|UNIDAD|UNID|UND|U|PCS|PZAS|PIEZAS)\b", up)
    n = Decimal(paquete.group(1)) if paquete else Decimal(1)
    if unidad == "m":
        largo = re.search(r"LONGITUD\s*(?:DE\s*)?(\d+(?:[.,]\d+)?)\s*(?:MTS?|METROS?)\b", up)
        if largo:
            return n * Decimal(largo.group(1).replace(",", "."))
        rollo = re.search(r"(\d+)\s*(?:MTS?|METROS)\b", up)
        if rollo and int(rollo.group(1)) >= 20:
            return Decimal(rollo.group(1))
        return defecto
    return n if paquete else defecto


def elegir_material(cat, cfg, clave: str, ciudad: str,
                    cantidad: Decimal = None):
    """None: material opcional sin stock suficiente en la ciudad (el kit lo omite)."""
    m = cfg.materiales[clave]
    if m.sku:
        p = cat.por_sku(m.sku)
        cands = [Candidato(p, {}, p.stock_en(ciudad) or 0)] if p else []
    elif m.buscar:
        patron = "".join(f"(?=.*{re.escape(w.upper())})" for w in m.buscar.palabras) or "."
        cands = candidatos(cat, [m.buscar.categoria], patron, ciudad, excluir=m.buscar.excluir)
    else:
        cands = []
    def costo_u(c: Candidato):
        return c.costo / unidades_por_item(c.p.nombre, m.unidad, m.unidad_compra)
    if m.opcional:
        def alcanza(c: Candidato) -> bool:     # unidades disponibles (ítems × unidades por ítem) >= lo pedido
            disp = c.p.stock_total if c.stock is None else c.stock
            return disp * unidades_por_item(c.p.nombre, m.unidad, m.unidad_compra) >= (cantidad or 1)
        cands = [c for c in cands if alcanza(c)]
        if not cands:
            return None
    con_stock = [c for c in cands if _st(c) > 0]
    if con_stock:
        c = min(con_stock, key=costo_u)
        return Material(clave, m.descripcion, m.unidad, costo_u(c), c.p.sku, c.p.categoria, c.stock,
                        precio_item=c.costo)
    sin_verificar = [c for c in cands if c.stock is None]
    if sin_verificar:
        c = min(sin_verificar, key=costo_u)
        return Material(clave, m.descripcion, m.unidad, costo_u(c), c.p.sku, c.p.categoria, None,
                        [alerta_no_verificado(c, ciudad)], precio_item=c.costo)
    return Material(clave, m.descripcion, m.unidad, m.precio_ref, None, None, None,
                    [f"Material '{clave}' sin SKU con stock en {ciudad}: se usa precio de referencia"])
