"""Dinero con dos decimales, sin flotantes."""
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0.00")


def money(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
