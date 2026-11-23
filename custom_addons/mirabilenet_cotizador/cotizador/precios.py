"""Aritmética de precios del cotizador: recargo, redondeo comercial, impuestos y tipo de cambio.

Traída de referencia/core/pricing.py (Cotizador DigiCorp). Todo en Decimal con ROUND_HALF_UP.
La configuración llega como `Config` (la arma Odoo desde sus reglas y parámetros), sin YAML.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

D0 = Decimal("0")
CENT = Decimal("0.01")


def D(v):
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v if v not in (None, "") else 0))


def money(v):
    return D(v).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Escalon:
    hasta: Decimal      # costo del ítem < hasta
    recargo: Decimal


@dataclass
class Buscar:
    categoria: str
    palabras: list = field(default_factory=list)   # todas deben aparecer en el nombre
    excluir: str = None                            # regex: descarta si aparece


@dataclass
class Material:
    descripcion: str
    precio_ref: Decimal
    buscar: Buscar = None
    sku: str = None
    unidad: str = "u"
    unidad_compra: Decimal = Decimal("1")
    opcional: bool = False     # sin stock suficiente en la ciudad: se quita del kit


@dataclass
class Tarifa:
    precio: Decimal
    unidad: str
    descripcion: str


@dataclass
class Viaticos:
    ciudad_base: str = "La Paz"
    por_ciudad: dict = field(default_factory=dict)
    por_km: Decimal = D0
    descripcion: str = "Movilidad y viáticos"


@dataclass
class Config:
    moneda: str = "Bs"
    recargo_defecto: Decimal = Decimal("0.30")
    recargo_maximo: Decimal = Decimal("0.75")
    recargo_maximo_bajo: Decimal = Decimal("1.50")
    por_categoria: dict = field(default_factory=dict)     # «CAMARAS IP» -> 0.30
    por_costo: list = field(default_factory=list)          # [Escalon]
    iva: Decimal = Decimal("0.13")
    it: Decimal = Decimal("0.03")
    modo_impuestos: str = "agregar"                        # agregar | bruto
    facturar_por_defecto: bool = True
    vigencia_dias: int = 5
    redondeo_multiplo: Decimal = Decimal("5")
    redondeo_umbral_bajo: Decimal = Decimal("50")
    redondeo_multiplo_bajo: Decimal = Decimal("0.5")
    redondeo_total: Decimal = D0
    precio_max_horas: float = 24
    marcas_preferidas: list = field(default_factory=list)
    bonus_marca_preferida: float = 0.15
    tipo_cambio_manual: Decimal = Decimal("6.96")
    # almacenamiento
    bitrate_h265_mbps: dict = field(default_factory=lambda: {
        1: 1.0, 2: 2.0, 3: 2.5, 4: 3.0, 5: 3.5, 6: 4.0, 8: 6.0, 12: 8.0})
    factor_codec: dict = field(default_factory=lambda: {
        "H.265": 1.0, "H.265+": 0.6, "H.264": 1.8, "H.264+": 1.1})
    factor_modo: dict = field(default_factory=lambda: {"continua": 1.0, "movimiento": 0.4})
    margen_almacenamiento: float = 0.10
    consumo_camara_w: dict = field(default_factory=lambda: {
        "defecto": 6.5, "full_color": 8, "PT": 10, "PTZ": 25})
    materiales: dict = field(default_factory=dict)    # clave -> Material
    mano_obra: dict = field(default_factory=dict)     # clave -> Tarifa
    viaticos: Viaticos = field(default_factory=Viaticos)

    def __post_init__(self):
        self.por_categoria = {k.upper().strip(): D(v) for k, v in self.por_categoria.items()}
        self.por_costo = sorted((e if isinstance(e, Escalon) else Escalon(D(e[0]), D(e[1]))
                                 for e in self.por_costo), key=lambda e: e.hasta)

    def escalon(self, costo):
        if costo is None:
            return None
        return next((e for e in self.por_costo if D(costo) < e.hasta), None)

    def tope(self, costo=None):
        return self.recargo_maximo_bajo if self.escalon(costo) else self.recargo_maximo

    def validar(self):
        """Lista de recargos fuera de los topes (vacía si todo está bien)."""
        malos = [("defecto", self.recargo_defecto)] if not (
            D0 <= self.recargo_defecto <= self.recargo_maximo) else []
        malos += [(k, v) for k, v in self.por_categoria.items()
                  if not D0 <= v <= self.recargo_maximo]
        malos += [("< %s Bs" % e.hasta, e.recargo) for e in self.por_costo
                  if not D0 <= e.recargo <= self.recargo_maximo_bajo]
        return malos


def recargo_para(cfg, categoria, subcategoria=None, costo_item=None):
    """Escalón por costo del ítem (ítems baratos) > subcategoría > categoría > defecto."""
    escalon = cfg.escalon(costo_item)
    if escalon:
        return escalon.recargo
    for clave in (subcategoria, categoria):
        if clave and clave.upper().strip() in cfg.por_categoria:
            return cfg.por_categoria[clave.upper().strip()]
    return cfg.recargo_defecto


def validar_recargo(cfg, recargo, costo_item=None):
    """Para recargos manuales: error si supera el tope (mayor para ítems baratos)."""
    r = D(recargo)
    tope = cfg.tope(costo_item)
    if r < 0 or r > tope:
        raise ValueError("Recargo de %.0f %% fuera del rango permitido (0 a %.0f %%)"
                         % (r * 100, tope * 100))
    return r


def redondear_arriba(valor, multiplo):
    multiplo = D(multiplo)
    if multiplo <= 0:
        return money(valor)
    return money((D(valor) / multiplo).to_integral_value(rounding=ROUND_CEILING) * multiplo)


def precio_venta(cfg, costo, recargo):
    """costo × (1 + recargo), redondeado hacia arriba según la escala."""
    bruto = D(costo) * (1 + D(recargo))
    multiplo = cfg.redondeo_multiplo_bajo if bruto < cfg.redondeo_umbral_bajo \
        else cfg.redondeo_multiplo
    return redondear_arriba(bruto, multiplo)


@dataclass(frozen=True)
class Impuestos:
    subtotal: Decimal
    iva: Decimal
    it: Decimal
    redondeo: Decimal
    total: Decimal

    @property
    def impuestos(self):
        return self.iva + self.it


def calcular_impuestos(cfg, subtotal, facturar):
    sub = money(subtotal)
    if not facturar:
        iva = it = D0
        total = sub
    elif cfg.modo_impuestos == "agregar":
        iva = money(sub * cfg.iva)
        it = money(sub * cfg.it)
        total = sub + iva + it
    else:  # bruto: total tal que total menos el 16 % del total = subtotal
        tasa = cfg.iva + cfg.it
        total = money(sub / (1 - tasa))
        iva = money(total * cfg.iva)
        it = total - sub - iva
    redondeo = D0
    if cfg.redondeo_total > 0:
        nuevo = redondear_arriba(total, cfg.redondeo_total)
        redondeo, total = nuevo - total, nuevo
    return Impuestos(sub, iva, it, redondeo, total)


@dataclass(frozen=True)
class TipoCambio:
    valor: Decimal
    fecha: date = None
    fuente: str = "manual"


def a_usd(monto, tc):
    return money(D(monto) / D(tc.valor)) if D(tc.valor) else D0
