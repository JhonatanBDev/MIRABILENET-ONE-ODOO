"""Indicadores de negocio de un ISP, sin Odoo: ARPU, churn, recaudación, antigüedad de cartera y
variación contra el periodo anterior. None quiere decir «no se puede calcular» (no es 0)."""

#: Tramos de antigüedad de la cartera: (clave, etiqueta, desde días, hasta días o None).
TRAMOS = (
    ("0_30", "0–30 días", 0, 30),
    ("31_60", "31–60 días", 31, 60),
    ("61_90", "61–90 días", 61, 90),
    ("90_mas", "Más de 90 días", 91, None),
)


def arpu(mrr, servicios):
    """Ingreso medio por servicio que factura."""
    if not servicios:
        return None
    return round((mrr or 0.0) / servicios, 2)


def churn(bajas, activos_al_inicio):
    """Porcentaje de bajas del mes sobre los servicios que había al empezar el mes."""
    if not activos_al_inicio:
        return None
    return round(100.0 * (bajas or 0) / activos_al_inicio, 1)


def recaudacion(cobrado, facturado):
    """Porcentaje de lo facturado que se cobró."""
    if not facturado:
        return None
    return round(100.0 * (cobrado or 0.0) / facturado, 1)


def variacion(actual, anterior):
    """% de cambio contra el periodo anterior; None si antes no hubo nada con qué comparar."""
    if actual is None or not anterior:
        return None
    return round(100.0 * (actual - anterior) / abs(anterior), 1)


def tramo(dias_vencida):
    """La clave del tramo para una factura vencida hace `dias_vencida` días."""
    for clave, _etiqueta, desde, hasta in TRAMOS:
        if dias_vencida >= desde and (hasta is None or dias_vencida <= hasta):
            return clave
    return TRAMOS[0][0]


def antiguedad(facturas, hoy):
    """Agrupa facturas vencidas por tramo. `facturas`: iterable de (vencimiento, saldo, cliente).

    Devuelve una fila por tramo, siempre los cuatro, con monto, facturas y clientes distintos.
    """
    filas = {clave: {"clave": clave, "etiqueta": etiqueta, "monto": 0.0, "facturas": 0,
                     "clientes": set()}
             for clave, etiqueta, _desde, _hasta in TRAMOS}
    for vencimiento, saldo, cliente in facturas:
        if not vencimiento or vencimiento >= hoy:
            continue
        fila = filas[tramo((hoy - vencimiento).days)]
        fila["monto"] += saldo or 0.0
        fila["facturas"] += 1
        fila["clientes"].add(cliente)
    resultado = []
    for clave, *_resto in TRAMOS:
        fila = filas[clave]
        fila["clientes"] = len(fila["clientes"])
        resultado.append(fila)
    return resultado
