"""Aritmética monetaria con Decimal. Nunca floats binarios para dinero."""

from decimal import Decimal, ROUND_HALF_UP

TWO = Decimal("0.01")


def dec(value):
    """Convierte a Decimal sin heredar el error binario de un float."""
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, float):
        return Decimal(repr(value))
    return Decimal(str(value))


def money(value):
    return dec(value).quantize(TWO, rounding=ROUND_HALF_UP)


def fmt(value):
    """Texto con exactamente 2 decimales, como exige el XSD."""
    return "%.2f" % money(value)
