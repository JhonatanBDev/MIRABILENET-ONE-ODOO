"""Cuentas del dashboard que no dependen de Odoo: periodos, meses y porcentajes."""
from datetime import date, timedelta

#: Periodos que ofrece la pantalla y cuántos días cubre cada uno (hoy incluido).
PERIODOS = {"hoy": 1, "7": 7, "30": 30, "90": 90}
MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def periodo_valido(periodo):
    return periodo if periodo in PERIODOS else "30"


def rango(periodo, hoy):
    """(desde, hasta) del periodo, los dos días incluidos."""
    dias = PERIODOS[periodo_valido(periodo)]
    return hoy - timedelta(days=dias - 1), hoy


def dias(desde, hasta):
    """Cada día entre desde y hasta, los dos incluidos."""
    return [desde + timedelta(days=n) for n in range((hasta - desde).days + 1)]


def inicio_de_mes(dia):
    return dia.replace(day=1)


def meses_atras(hoy, cantidad):
    """Los últimos `cantidad` meses, del más viejo al actual: (primer día, último día, etiqueta)."""
    resultado = []
    anio, mes = hoy.year, hoy.month
    for _ in range(cantidad):
        primero = date(anio, mes, 1)
        siguiente = date(anio + (mes == 12), mes % 12 + 1, 1)
        resultado.append((primero, siguiente - timedelta(days=1),
                          "%s %s" % (MESES[mes - 1], str(anio)[2:])))
        anio, mes = (anio - 1, 12) if mes == 1 else (anio, mes - 1)
    return list(reversed(resultado))


def porcentaje(parte, total):
    """Porcentaje con un decimal; None cuando no hay sobre qué calcular (no es 0)."""
    if not total:
        return None
    return round(100.0 * (parte or 0) / total, 1)


def disponible(total, usado):
    """Lo que queda libre; None si no hay total declarado."""
    if not total:
        return None
    return max(total - (usado or 0), 0)
