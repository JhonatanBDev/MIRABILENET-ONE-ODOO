"""Estructura de una cotización y sus totales.

`costo_unit`, `recargo`, `margen` y `proveedor` son datos INTERNOS: el PDF (Fase 3)
solo usa descripcion, cantidad, unidad, precio_unit y total.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from .precios import D0, a_usd, calcular_impuestos, money

GRUPOS = ["equipos", "materiales", "mano_obra", "viaticos"]


@dataclass
class Linea:
    grupo: str
    descripcion: str
    cantidad: Decimal
    unidad: str
    precio_unit: Decimal
    sku: str = None
    marca: str = None
    costo_unit: Decimal = None      # interno
    recargo: Decimal = None         # interno
    stock_ciudad: int = None        # interno
    motivo: str = None              # interno: por qué se eligió
    alertas: list = field(default_factory=list)

    @property
    def total(self):
        return money(self.precio_unit * self.cantidad)

    @property
    def costo_total(self):
        return money((self.costo_unit or D0) * self.cantidad)


@dataclass
class Cotizacion:
    cfg: object
    ciudad: str
    facturar: bool
    tipo_cambio: object
    titulo: str = ""
    fecha: date = field(default_factory=date.today)
    lineas: list = field(default_factory=list)
    almacenamiento: object = None
    alertas: list = field(default_factory=list)
    notas: list = field(default_factory=list)

    @property
    def vigencia_hasta(self):
        return self.fecha + timedelta(days=self.cfg.vigencia_dias)

    def subtotal_grupo(self, g):
        return sum((l.total for l in self.lineas if l.grupo == g), D0)

    @property
    def subtotal(self):
        return sum((l.total for l in self.lineas), D0)

    @property
    def impuestos(self):
        return calcular_impuestos(self.cfg, self.subtotal, self.facturar)

    @property
    def total(self):
        return self.impuestos.total

    @property
    def total_usd(self):
        return a_usd(self.total, self.tipo_cambio)

    # ---- internos
    @property
    def costo(self):
        return sum((l.costo_total for l in self.lineas if l.costo_unit is not None), D0)

    @property
    def margen_equipos_materiales(self):
        """Utilidad sobre equipos+materiales (sin impuestos)."""
        venta = self.subtotal_grupo("equipos") + self.subtotal_grupo("materiales")
        return venta - self.costo

    @property
    def utilidad_bruta(self):
        """Subtotal - costo de equipos/materiales (incluye mano de obra y viáticos)."""
        return self.subtotal - self.costo

    def todas_alertas(self):
        return self.alertas + [f"{l.sku or l.descripcion}: {a}" for l in self.lineas for a in l.alertas]
