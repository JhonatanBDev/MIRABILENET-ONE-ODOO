"""Del pedido escrito (o de los requisitos que arma la IA de n8n) a un kit listo para el motor.

Traído de referencia/core/ia.py (`normalizar` y `kit_desde_proyecto`), sin Ollama: lo que el
texto dice de forma explícita manda; lo que no dice queda con el valor por defecto y una duda.
"""
import copy

from . import pedido

PLANTILLAS = {("ip", "estandar"): "tienda_8", ("ip", "economica"): "tienda_8_eco",
              ("analogica", "estandar"): "tienda_8_analogico",
              ("analogica", "economica"): "casa_4_analogico"}
TIPOS_DEFECTO = {"interior": ["DOMO", "TURRET", "EYEBALL"], "exterior": ["BULLET", "TURRET", "EYEBALL"]}
MAX_CAMARAS = 64


class PedidoError(ValueError):
    pass


def requisitos_desde_texto(texto):
    """Requisitos del proyecto según las reglas. Lanza PedidoError si no dice cuántas cámaras."""
    h = pedido.analizar(texto)
    dudas = []

    def tipos_de(ubicacion):
        pedidos = [t for t in h.tipos if t in TIPOS_DEFECTO[ubicacion] or t in ("PT", "PTZ")]
        return pedidos or TIPOS_DEFECTO[ubicacion]

    if h.interior is not None or h.exterior is not None:
        camaras = [{"cantidad": min(n, MAX_CAMARAS), "ubicacion": u, "tipos": tipos_de(u)}
                   for u, n in (("interior", h.interior or 0), ("exterior", h.exterior or 0)) if n]
    elif h.total:
        ubicacion = "exterior" if h.solo_exterior else "interior"
        camaras = [{"cantidad": min(h.total, MAX_CAMARAS), "ubicacion": ubicacion,
                    "tipos": tipos_de(ubicacion)}]
        if not h.solo_exterior:
            dudas.append("El pedido no dice cuántas cámaras van afuera: se cotizaron todas para "
                         "interior")
    else:
        raise PedidoError("No encontré cuántas cámaras pide. Escriba por ejemplo «4 cámaras, "
                          "2 afuera».")
    gama = "economica" if h.economica else "estandar"
    tecnologia = h.tecnologia or ("analogica" if h.economica else "ip")
    if not h.tecnologia and h.economica:
        dudas.append("Pidió económico sin indicar tecnología: se cotizó analógico (HDCVI), que es "
                     "lo más barato. Cambie a IP si el cliente lo prefiere")
    return {
        "camaras": camaras, "resolucion_min": min(12.0, max(1.0, h.mp or 2)),
        "tecnologia": tecnologia, "gama": gama, "dias": min(90, max(1, h.dias or 15)),
        "disco_gb": h.disco_gb, "movimiento": h.movimiento, "metros": h.metros,
        "lugar": h.lugar, "dudas": dudas,
    }


def titulo(req):
    n = sum(int(c["cantidad"]) for c in req["camaras"])
    plural = "s" if n != 1 else ""
    tecno = ("analógica" + plural) if req["tecnologia"] == "analogica" else "IP"
    lugar = (req.get("lugar") + " · ") if req.get("lugar") else ""
    eco = " (económico)" if req["gama"] == "economica" else ""
    return "CCTV %s%s cámara%s %s%s" % (lugar, n, plural, tecno, eco)


def kit_desde_requisitos(req, kits):
    """Toma materiales y mano de obra de la plantilla que corresponde y pone las cámaras,
    tecnología, gama y grabación pedidas. `kits`: {clave: definición}."""
    clave = PLANTILLAS[(req["tecnologia"], req["gama"])]
    if clave not in kits:
        raise PedidoError("Falta el kit plantilla «%s»." % clave)
    base = copy.deepcopy(kits[clave])
    ip = req["tecnologia"] == "ip"
    base["nombre"] = req.get("titulo") or titulo(req)
    base.update(tecnologia=req["tecnologia"], gama=req["gama"], dias_grabacion=req["dias"],
                modo_grabacion="movimiento" if req.get("movimiento") else "continua",
                disco_gb=req.get("disco_gb"))
    base["camaras"] = [dict(c, resolucion_min=c.get("resolucion_min") or req["resolucion_min"],
                            **({"poe": True} if ip else {})) for c in req["camaras"]]
    n = sum(int(c["cantidad"]) for c in req["camaras"])
    if ip:
        base["nvr"] = {"poe_integrado": n <= 8, "canales_extra": 0}
        if n > 8:
            base.setdefault("mano_obra", {})["config_switch"] = 1
    return base
