"""Cuentas del dashboard que no dependen de Odoo: periodos, meses y porcentajes."""
from datetime import date, timedelta

#: Periodos fijos que ofrece la pantalla y cuántos días cubre cada uno (hoy incluido).
PERIODOS = {"hoy": 1, "7": 7, "30": 30, "90": 90}
#: Periodos por calendario o elegidos a mano.
OTROS = ("mes", "mes_anterior", "rango")
MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def periodo_valido(periodo):
    return periodo if periodo in PERIODOS or periodo in OTROS else "30"


def inicio_de_mes(dia):
    return dia.replace(day=1)


def fin_de_mes(dia):
    siguiente = date(dia.year + (dia.month == 12), dia.month % 12 + 1, 1)
    return siguiente - timedelta(days=1)


def rango(periodo, hoy, desde=None, hasta=None):
    """(desde, hasta) del periodo, los dos días incluidos.

    «rango» usa las fechas dadas (ordenadas, y nunca después de hoy); sin ellas, 30 días.
    """
    periodo = periodo_valido(periodo)
    if periodo == "mes":
        return inicio_de_mes(hoy), hoy
    if periodo == "mes_anterior":
        fin = inicio_de_mes(hoy) - timedelta(days=1)
        return inicio_de_mes(fin), fin
    if periodo == "rango":
        if not desde or not hasta:
            return rango("30", hoy)
        desde, hasta = sorted((desde, hasta))
        return desde, min(hasta, hoy) if desde <= hoy else hasta
    dias_periodo = PERIODOS[periodo]
    return hoy - timedelta(days=dias_periodo - 1), hoy


def anterior(desde, hasta):
    """El periodo del mismo largo inmediatamente antes, para comparar."""
    largo = (hasta - desde).days + 1
    return desde - timedelta(days=largo), desde - timedelta(days=1)


def dias(desde, hasta):
    """Cada día entre desde y hasta, los dos incluidos."""
    return [desde + timedelta(days=n) for n in range((hasta - desde).days + 1)]


def meses_atras(hoy, cantidad):
    """Los últimos `cantidad` meses, del más viejo al actual: (primer día, último día, etiqueta)."""
    resultado = []
    anio, mes = hoy.year, hoy.month
    for _ in range(cantidad):
        primero = date(anio, mes, 1)
        resultado.append((primero, fin_de_mes(primero), "%s %s" % (MESES[mes - 1], str(anio)[2:])))
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
