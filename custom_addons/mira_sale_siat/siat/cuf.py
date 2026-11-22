"""CufGenerator: Código Único de Factura.

Algoritmo publicado por el SIN:
  1. Concatenar, con ceros a la izquierda, NIT(13) + fecha/hora(17) +
     sucursal(4) + modalidad(1) + tipo emisión(1) + tipo factura(1) +
     documento sector(2) + número de factura(10) + punto de venta(4).
  2. Agregar el dígito verificador Módulo 11.
  3. Convertir el número resultante a base 16.
  4. Concatenar el código de control del CUFD.
"""

_FIELDS = (
    # (nombre, longitud)
    ("nit", 13),
    ("timestamp", 17),
    ("branch", 4),
    ("modality", 1),
    ("emission_type", 1),
    ("invoice_type", 1),
    ("sector", 2),
    ("number", 10),
    ("pos", 4),
)


def mod11(cadena, num_dig=1, lim_mult=9, x10=False):
    """Dígito(s) verificador(es) Módulo 11, tal como lo publica el SIN."""
    if not x10:
        num_dig = 1
    for _n in range(num_dig):
        suma = 0
        mult = 2
        for ch in reversed(cadena):
            suma += mult * int(ch)
            mult += 1
            if mult > lim_mult:
                mult = 2
        dig = ((suma * 10) % 11) % 10 if x10 else suma % 11
        if dig == 10:
            cadena += "1"
        elif dig == 11:
            cadena += "0"
        else:
            cadena += str(dig)
    return cadena[-num_dig:]


def format_timestamp(dt):
    """yyyyMMddHHmmssSSS a partir de un datetime en hora fiscal (Bolivia)."""
    return dt.strftime("%Y%m%d%H%M%S") + "%03d" % (dt.microsecond // 1000)


def build_cuf(nit, emission_dt, branch, modality, emission_type, invoice_type,
              sector, number, pos, control_code):
    """Devuelve el CUF. `emission_dt` debe estar en hora fiscal de Bolivia."""
    if not control_code:
        raise ValueError("Falta el código de control del CUFD.")
    values = {
        "nit": nit,
        "timestamp": format_timestamp(emission_dt),
        "branch": branch,
        "modality": modality,
        "emission_type": emission_type,
        "invoice_type": invoice_type,
        "sector": sector,
        "number": number,
        "pos": pos,
    }
    parts = []
    for name, length in _FIELDS:
        text = str(values[name]).strip()
        if not text.isdigit():
            raise ValueError("El campo %s del CUF debe ser numérico: %r" % (name, text))
        if len(text) > length:
            raise ValueError(
                "El campo %s del CUF excede %d dígitos: %r" % (name, length, text))
        parts.append(text.zfill(length))
    cadena = "".join(parts)
    cadena += mod11(cadena, 1, 9, False)
    return "%X" % int(cadena) + control_code
