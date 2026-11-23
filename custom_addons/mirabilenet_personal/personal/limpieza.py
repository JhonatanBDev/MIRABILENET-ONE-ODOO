"""Lectura y limpieza de la plantilla del personal, sin Odoo.

Una fila por persona. Columnas (el encabezado puede venir con tildes, mayúsculas o espacios):
nombre, usuario, correo, whatsapp, rol, region, sucursal, zonas, jefe, activo.
"""
import csv
import io
import re
import unicodedata

#: Alias de encabezado -> clave interna.
COLUMNAS = {
    "nombre": "nombre", "nombre completo": "nombre", "nombre y apellido": "nombre",
    "usuario": "usuario", "login": "usuario", "usuario de ingreso": "usuario",
    "correo": "correo", "email": "correo", "correo electronico": "correo",
    "whatsapp": "whatsapp", "celular": "whatsapp", "telefono": "whatsapp",
    "numero de whatsapp": "whatsapp",
    "rol": "rol", "cargo": "rol", "puesto": "rol",
    "region": "region", "sucursal": "sucursal",
    "zonas": "zonas", "zonas que atiende": "zonas", "zona": "zonas",
    "jefe": "jefe", "jefe directo": "jefe", "supervisor": "jefe",
    "activo": "activo",
}
OBLIGATORIAS = ("nombre", "usuario", "rol")
#: Cómo puede venir escrito cada rol -> rol del sistema. Los cargos son los roles que ya existen.
ROLES = {
    "superadmin": "superadmin", "superadministrador": "superadmin",
    "gerencia": "gerencia", "gerente": "gerencia", "gerencia general": "gerencia",
    "gerente general": "gerencia",
    "admin regional": "admin_regional", "administrador regional": "admin_regional",
    "admin_regional": "admin_regional", "subgerente": "admin_regional",
    "noc": "noc",
    "tecnico": "tecnico", "tecnico de campo": "tecnico",
    "finanzas": "finanzas", "cajero": "cajero", "cobrador": "cobrador",
    "almacenista": "almacenista", "vendedor": "vendedor",
    "operador de camaras": "operador_camaras", "operador_camaras": "operador_camaras",
    "auditor": "auditor", "pasante": "pasante", "practicante": "pasante",
}
SI = {"si", "sí", "s", "1", "x", "true", "activo", "yes"}
NO = {"no", "n", "0", "false", "inactivo", "baja"}


def clave(texto):
    """Encabezado o valor comparable: sin tildes, minúsculas, espacios simples."""
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[\s_]+", " ", texto.strip().lower())


def leer_csv(contenido):
    """Filas como dicts con claves internas. Acepta ; o , y BOM."""
    if isinstance(contenido, bytes):
        for codec in ("utf-8-sig", "latin-1"):
            try:
                contenido = contenido.decode(codec)
                break
            except UnicodeDecodeError:
                continue
    muestra = contenido[:2000]
    delimitador = ";" if muestra.count(";") >= muestra.count(",") else ","
    lector = csv.reader(io.StringIO(contenido), delimiter=delimitador)
    filas = [f for f in lector if any(c.strip() for c in f)]
    if not filas:
        return [], []
    encabezado = [COLUMNAS.get(clave(c), "") for c in filas[0]]
    faltan = [c for c in OBLIGATORIAS if c not in encabezado]
    datos = []
    for numero, fila in enumerate(filas[1:], start=2):
        registro = {"fila": numero}
        for indice, columna in enumerate(encabezado):
            if columna and indice < len(fila):
                registro[columna] = fila[indice].strip()
        datos.append(registro)
    return datos, faltan


def whatsapp(texto):
    """Solo dígitos; un número boliviano de 8 dígitos se completa con 591."""
    digitos = re.sub(r"\D", "", texto or "")
    if digitos.startswith("00"):
        digitos = digitos[2:]
    if len(digitos) == 8 and digitos[0] in "67":
        digitos = "591" + digitos
    return digitos


def lista(texto):
    """'Z1, Z2; Z3' -> ['Z1', 'Z2', 'Z3'] sin repetidos."""
    vistos = []
    for parte in re.split(r"[,;/|]", texto or ""):
        parte = parte.strip()
        if parte and parte.upper() not in [v.upper() for v in vistos]:
            vistos.append(parte)
    return vistos


def activo(texto):
    valor = clave(texto)
    if not valor:
        return True
    if valor in NO:
        return False
    return True


def limpiar(filas):
    """Valida cada fila. Devuelve (filas limpias, errores por fila)."""
    limpias, errores = [], []
    usuarios = {}
    numeros = {}
    for fila in filas:
        problemas = []
        nombre = re.sub(r"\s+", " ", fila.get("nombre", "")).strip()
        usuario = fila.get("usuario", "").strip().lower()
        rol = ROLES.get(clave(fila.get("rol", "")))
        numero = whatsapp(fila.get("whatsapp", ""))
        if not nombre:
            problemas.append("falta el nombre")
        if not usuario:
            problemas.append("falta el usuario")
        elif usuario in usuarios:
            problemas.append("usuario repetido (fila %s)" % usuarios[usuario])
        if not rol:
            problemas.append("rol desconocido: «%s»" % fila.get("rol", ""))
        if fila.get("whatsapp") and not (10 <= len(numero) <= 15):
            problemas.append("WhatsApp no válido: «%s»" % fila.get("whatsapp"))
        elif numero and numero in numeros:
            problemas.append("WhatsApp repetido (fila %s)" % numeros[numero])
        correo = fila.get("correo", "").strip().lower()
        if correo and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo):
            problemas.append("correo no válido: «%s»" % correo)
        if problemas:
            errores.append((fila["fila"], "; ".join(problemas)))
            continue
        usuarios[usuario] = fila["fila"]
        if numero:
            numeros[numero] = fila["fila"]
        limpias.append({
            "fila": fila["fila"], "nombre": nombre, "usuario": usuario, "correo": correo,
            "whatsapp": numero, "rol": rol, "region": fila.get("region", "").strip(),
            "sucursal": fila.get("sucursal", "").strip(), "zonas": lista(fila.get("zonas")),
            "jefe": fila.get("jefe", "").strip().lower(), "activo": activo(fila.get("activo")),
        })
    return limpias, errores


def avisos_csv(avisos):
    """CSV (;) de lo que no se pudo cargar o hay que revisar: fila, usuario, detalle."""
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow(["fila", "usuario", "detalle"])
    for fila, usuario, detalle in avisos:
        escritor.writerow([fila, usuario, detalle])
    return ("﻿" + salida.getvalue()).encode("utf-8")
