"""Estimación de almacenamiento para NVR (traída de referencia/core/storage.py). Es una ESTIMACIÓN: el bitrate real depende
de la escena, fps, iluminación nocturna y configuración (VBR/CBR, smart codec)."""
from dataclasses import dataclass, field

GB_DIA_POR_MBPS = 86400 / 8 / 1000   # 1 Mbps sostenido = 10.8 GB/día (decimal)


@dataclass(frozen=True)
class GrupoCamaras:
    cantidad: int
    resolucion_mp: float


@dataclass
class CalculoAlmacenamiento:
    dias: int
    codec: str
    modo: str
    lineas: list = field(default_factory=list)
    tb_requeridos: float = 0.0
    dias_por_modo: dict = field(default_factory=dict)   # solo con disco fijo

    def texto(self) -> str:
        return "\n".join(self.lineas)


def bitrate_mbps(cfg, mp: float, codec: str) -> float:
    """Interpola linealmente la tabla H.265 por MP y aplica el factor de códec."""
    tabla = sorted((float(k), float(v)) for k, v in cfg.bitrate_h265_mbps.items())
    if mp <= tabla[0][0]:
        base = tabla[0][1]
    elif mp >= tabla[-1][0]:
        base = tabla[-1][1] * mp / tabla[-1][0]
    else:
        for (x0, y0), (x1, y1) in zip(tabla, tabla[1:]):
            if x0 <= mp <= x1:
                base = y0 + (y1 - y0) * (mp - x0) / (x1 - x0)
                break
    try:
        factor = cfg.factor_codec[codec]
    except KeyError as e:
        raise ValueError(f"Códec desconocido '{codec}'. Opciones: {', '.join(cfg.factor_codec)}") from e
    return base * factor


def calcular(cfg, grupos, dias: int,
             codec: str = "H.265", modo: str = "continua") -> CalculoAlmacenamiento:
    if modo not in cfg.factor_modo:
        raise ValueError(f"Modo '{modo}' desconocido. Opciones: {', '.join(cfg.factor_modo)}")
    fm = cfg.factor_modo[modo]
    c = CalculoAlmacenamiento(dias, codec, modo)
    total_gb = 0.0
    for g in grupos:
        mbps = bitrate_mbps(cfg, g.resolucion_mp, codec)
        gb_dia = mbps * GB_DIA_POR_MBPS * fm
        gb = gb_dia * dias * g.cantidad
        total_gb += gb
        c.lineas.append(f"{g.cantidad} cám × {g.resolucion_mp:g} MP {codec} ≈ {mbps:.1f} Mbps"
                        f"{f' × {fm:g} ({modo})' if fm != 1 else ''} → {gb_dia:.1f} GB/día c/u"
                        f" × {dias} días = {gb / 1000:.2f} TB")
    tb = total_gb / 1000 * (1 + cfg.margen_almacenamiento)
    c.tb_requeridos = round(tb, 2)
    c.lineas.append(f"Subtotal {total_gb / 1000:.2f} TB + {cfg.margen_almacenamiento:.0%} de reserva ={tb:.2f} TB requeridos")
    c.lineas.append("Estimación: el consumo real varía según escena, fps, visión nocturna y configuración.")
    return c


def calcular_disco_fijo(cfg, grupos, tb: float, etiqueta: str,
                        codec: str = "H.265", modo: str = "continua") -> CalculoAlmacenamiento:
    """El cliente pidió un disco concreto (p. ej. 500 GB): en vez de dimensionar el disco,
    se informa cuántos días graba. `tb_requeridos` queda igual al disco pedido."""
    if modo not in cfg.factor_modo:
        raise ValueError(f"Modo '{modo}' desconocido. Opciones: {', '.join(cfg.factor_modo)}")
    c = CalculoAlmacenamiento(0, codec, modo)
    gb_dia_continuo = 0.0
    for g in grupos:
        mbps = bitrate_mbps(cfg, g.resolucion_mp, codec)
        gb_dia = mbps * GB_DIA_POR_MBPS
        gb_dia_continuo += gb_dia * g.cantidad
        c.lineas.append(f"{g.cantidad} cám × {g.resolucion_mp:g} MP {codec} ≈ {mbps:.1f} Mbps → {gb_dia:.1f} GB/día c/u")
    util_gb = tb * 1000 / (1 + cfg.margen_almacenamiento)
    dias = {m: (util_gb / (gb_dia_continuo * f) if gb_dia_continuo else 0.0) for m, f in cfg.factor_modo.items()}
    c.dias = int(dias[modo])
    c.dias_por_modo = dias
    c.tb_requeridos = round(tb, 3)
    como = {"continua": "en grabación continua", "movimiento": "grabando solo con movimiento"}
    otros = [f"≈ {d:.0f} días {como.get(m, m)}" for m, d in dias.items() if m != modo]
    c.lineas.append(f"Disco de {etiqueta} → ≈ {dias[modo]:.0f} días {como.get(modo, modo)}"
                    + (f" ({'; '.join(otros)})" if otros else ""))
    c.lineas.append("Estimación: el consumo real varía según escena, fps, visión nocturna y configuración.")
    return c
