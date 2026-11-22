"""Lectura y limpieza de una planilla de cartera (clientes, servicios, PPPoE y ONU).

No importa nada de Odoo: recibe bytes y devuelve filas limpias con sus avisos. Lo que no se
puede deducir no se inventa: queda vacío y se anota para revisar en campo.
"""
import collections
import csv
import datetime
import io
import re
import unicodedata

#: Columna lógica -> encabezados aceptados (ya normalizados con ``clave``).
COLUMNAS = {
    "nombre": ("nombre", "cliente", "nombre_completo", "titular"),
    "precio": ("precio_del_paquete", "precio", "precio_mensual", "mensualidad"),
    "usuario_pppoe": ("usuario_pppoe", "pppoe", "usuario"),
    "perfil": ("plan_win_box", "plan_winbox", "perfil_winbox", "perfil", "plan"),
    "modalidad": ("modalidad_de_pago", "modalidad", "tipo_de_pago"),
    "ip": ("ip_remota", "ip_fija", "ip"),
    "ci": ("c_i", "ci", "carnet", "carnet_de_identidad", "documento", "nit"),
    "telefono": ("telefono", "celular", "whatsapp"),
    "barrio": ("barrio", "zona_barrio"),
    "direccion": ("direccion", "direccion_de_instalacion", "referencia"),
    "marca": ("marca", "marca_onu"),
    "modelo": ("modelo", "modelo_onu"),
    "serie": ("no_de_serie", "n_de_serie", "numero_de_serie", "serie", "serial"),
    "mac": ("no_mac", "n_mac", "mac"),
    "fecha_solicitud": ("fecha_solicitud", "fecha_de_solicitud"),
    "fecha_activacion": ("fecha_activacion", "fecha_de_activacion", "fecha_alta",
                         "fecha_de_alta"),
    "latitud": ("latitud", "lat"),
    "longitud": ("longitud", "lon", "lng"),
    "caja_nap": ("caja_nap", "nap", "caja", "codigo_nap", "codigo_de_caja"),
    "puerto": ("puerto", "puerto_nap", "n_puerto", "no_puerto", "numero_de_puerto"),
}
OBLIGATORIAS = ("nombre", "usuario_pppoe", "perfil", "precio")

SIN_DATO = {"", "SIN DATO", "SIN DATOS", "ACTUALIZAR", "S/D", "SD", "-", "0", "N/A", "NA"}
#: Límites de Bolivia: una coordenada fuera de ellos es un error de tipeo.
LAT_BOLIVIA = (-23.0, -9.5)
LON_BOLIVIA = (-70.0, -57.4)

BARRIO_CORRECCIONES = {
    "24 DE SEPRIEMBRE": "24 DE SEPTIEMBRE", "LUI ESPINAL": "LUIS ESPINAL",
    "AMBORO2": "AMBORO 2", "AMBORO I": "AMBORO 1",
    "CRISTO ES LA RESPUESTA": "CRISTO LA RESPUESTA",
    "VILLA ESTUDIANTE": "VILLA DEL ESTUDIANTE", "BELEN": "VILLA BELEN",
}
EXPEDIDO = {"SC": "SC", "SCZ": "SC", "S.C.": "SC", "S.C": "SC", "SC.": "SC", "CBBA": "CB",
            "CBBA.": "CB", "CB": "CB", "ORURO": "OR", "OR": "OR", "LP": "LP", "LPZ": "LP",
            "PT": "PT", "PTS": "PT", "CH": "CH", "CHQ": "CH", "TJ": "TJ", "TJA": "TJ",
            "BE": "BN", "BN": "BN", "PA": "PD", "PD": "PD"}
MARCAS = {"V-SOL": "V-SOL", "V-SOL_TV": "V-SOL", "V-SOL_24": "V-SOL", "V-SOL-CATV": "V-SOL",
          "VSOL": "V-SOL", "C-DATA": "C-DATA", "C- DATA": "C-DATA", "CDATA": "C-DATA",
          "HUAWEI": "HUAWEI", "ZTE": "ZTE", "LANLY": "LANLY", "TP-LINK": "TP-LINK",
          "XPON ONU GENERICO": "GENERICO XPON", "GENERICO": "GENERICO XPON"}
MODELOS = {"V-2802GW": "V2802GW", "2802GW": "V2802GW", "V282GW": "V2802GW",
           "V28026W": "V2802GW", "FD51GW-X-R310": "FD511GW-X-R310",
           "FD511GWX": "FD511GW-X-R310", "ED511GW-XR310": "ED511GW-X-R310",
           "EG88141AS": "EG8141A5"}
MODALIDADES = {"prepago": "prepago", "pre_pago": "prepago", "pre": "prepago",
               "pospago": "pospago", "pos_pago": "pospago", "postpago": "pospago",
               "post_pago": "pospago", "pos": "pospago"}


def clave(texto):
    """«No. De SERIE» -> «no_de_serie»; «C.I.» -> «c_i»; sin tildes ni mayúsculas."""
    texto = (texto or "").replace("﻿", "").strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", texto).strip("_")


def leer_csv(data):
    """Bytes de un CSV con «;» o «,» -> (columnas lógicas encontradas, filas, desconocidas).

    Cada fila es un dict con las columnas lógicas y ``fila`` (número de línea en el archivo).
    """
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    lineas = texto.splitlines()
    while lineas and not lineas[0].strip():
        lineas.pop(0)
    if not lineas:
        raise ValueError("el archivo está vacío")
    separador = ";" if lineas[0].count(";") >= lineas[0].count(",") else ","
    lector = csv.reader(io.StringIO("\n".join(lineas), newline=""), delimiter=separador)
    encabezado = [clave(h) for h in next(lector)]
    alias = {a: logica for logica, nombres in COLUMNAS.items() for a in nombres}
    posiciones, desconocidas = {}, []
    for i, nombre in enumerate(encabezado):
        logica = alias.get(nombre)
        if logica and logica not in posiciones:
            posiciones[logica] = i
        elif nombre:
            desconocidas.append(nombre)
    filas = []
    for numero, valores in enumerate(lector, start=2):
        if not any(v.strip() for v in valores):
            continue
        fila = {logica: re.sub(r"\s+", " ", valores[i]).strip() if i < len(valores) else ""
                for logica, i in posiciones.items()}
        fila["fila"] = numero
        filas.append(fila)
    return set(posiciones), filas, desconocidas


def sin_dato(valor):
    return (valor or "").strip().upper() in SIN_DATO


def barrio(valor):
    b = re.sub(r"^(B\s*/|B\.|BARRIO)\s*", "", (valor or "").upper()).strip()
    return "" if sin_dato(b) else BARRIO_CORRECCIONES.get(b, b)


def documento(valor):
    """-> (número, complemento, expedido, nota, para_campo)."""
    if sin_dato(valor) or (valor or "").upper() == "PRUEBA":
        return "", "", "", "sin C.I.", True
    u = valor.upper().replace(" ", "")
    if u.startswith("E-"):
        return u, "", "", "documento de extranjero", False
    m = re.fullmatch(r"(\d{5,10})(?:-(\w{2}))?([A-Z.]*)", u)
    if not m:
        return "", "", "", "C.I. ilegible: %s" % valor, True
    numero, complemento, extension = m.groups()
    expedido = EXPEDIDO.get(extension, "") if extension else ""
    if extension and not expedido:
        return numero, (complemento or ""), "", "expedido ilegible: %s" % extension, True
    return numero, (complemento or ""), expedido, "", False


def mac(valor):
    """-> (MAC de 12 hexadecimales o vacía, nota, para_campo)."""
    if sin_dato(valor) or (valor or "").upper() == "PRUEBA":
        return "", "sin MAC", True
    u = re.sub(r"\(.*?\)", "", valor.upper())
    u = re.sub(r"[:\-\s.]", "", u).replace("O", "0")
    if re.fullmatch(r"[0-9A-F]{12}", u):
        return u, ("" if u == valor.upper() else "MAC corregida (%s)" % valor), False
    return "", "MAC ilegible: %s" % valor, True


def equipo(marca, modelo):
    """-> (marca, modelo, notas)."""
    m_original = (modelo or "").strip()
    marca_n = MARCAS.get((marca or "").strip().upper(), "")
    modelo_n = m_original.upper()
    notas = []
    if sin_dato(modelo_n) or modelo_n == "PRUEBA":
        modelo_n = ""
    if re.fullmatch(r"(HGW|WGD)-[0-9A-F]{4,6}", modelo_n):
        notas.append("modelo %s parece el nombre de la red wifi" % modelo_n)
        modelo_n = ""
    elif re.fullmatch(r"(V\d{10,11}|GPON[0-9A-F]{8})", modelo_n):
        notas.append("en el modelo venía un número de serie: %s" % modelo_n)
        modelo_n = ""
    elif modelo_n in ("4 PUERTOS", "G/EPON ONU"):
        notas.append("modelo no indicado (%s)" % m_original)
        modelo_n = ""
    if modelo_n in MODELOS:
        notas.append("modelo corregido (%s)" % m_original)
        modelo_n = MODELOS[modelo_n]
    if not marca_n and not sin_dato(marca) and (marca or "").upper() != "PRUEBA":
        notas.append("marca desconocida: %s" % marca)
        marca_n = (marca or "").strip().upper()
    return marca_n, modelo_n, notas


def fecha(valor):
    texto = (valor or "").strip()
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def coordenada(valor):
    texto = (valor or "").strip().replace(" ", "")
    if not texto:
        return None
    if texto.count(",") == 1 and "." not in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def precio(valor):
    texto = (valor or "").strip().replace(" ", "")
    for simbolo in ("BS.", "BS", "BOB", "$"):
        texto = texto.upper().replace(simbolo, "")
    texto = texto.replace(",", ".")
    try:
        numero = float(texto)
    except ValueError:
        return None
    return numero if numero >= 0 else None


def puerto(valor):
    """«3», «P3», «Puerto 3» -> 3. ``None`` si no hay número."""
    m = re.search(r"\d+", valor or "")
    return int(m.group(0)) if m else None


def nombre(valor):
    """Separa las notas que se escribieron dentro del nombre («+ CATV», «EN WS ...»)."""
    n = (valor or "").upper().strip()
    m = re.search(r"\s*(\+.*|\bEN WS\b.*)$", n)
    if m:
        return n[:m.start()].strip(), m.group(1).strip(" +")
    return n, ""


def velocidad(perfil):
    """«35MBPS-2026140» -> (35, False); «35 MBPS-2026 CATV» -> (35, True)."""
    m = re.match(r"\s*(\d+)\s*MB", (perfil or "").upper())
    return (int(m.group(1)) if m else 0), "CATV" in (perfil or "").upper()


def codigo(texto):
    return re.sub(r"[^A-Z0-9]+", "-", (texto or "").upper()).strip("-")


def limpiar(filas):
    """Filas leídas -> (registros listos, avisos).

    Cada aviso es un dict ``fila, cliente, que_revisar``. Un registro con ``error`` no se
    importa.
    """
    registros, avisos = [], []
    for f in filas:
        obs, campo = [], []
        nombre_limpio, nota = nombre(f.get("nombre"))
        if "PRUEBA" in nombre_limpio.split():
            avisos.append({"fila": f["fila"], "cliente": nombre_limpio,
                           "que_revisar": "fila de prueba: no se importa"})
            continue
        if nota:
            obs.append("Nota en el nombre: " + nota)
        error = []
        if not nombre_limpio:
            error.append("sin nombre")
        if not f.get("usuario_pppoe"):
            error.append("sin usuario PPPoE")
        monto = precio(f.get("precio"))
        if monto is None:
            error.append("precio ilegible: %s" % (f.get("precio") or "vacío"))
        perfil = f.get("perfil", "")
        mbps, tv = velocidad(perfil)
        if not perfil:
            error.append("sin plan / perfil de Winbox")
        ci, complemento, expedido, nota_ci, ci_campo = documento(f.get("ci"))
        if nota_ci:
            (campo if ci_campo else obs).append(nota_ci)
        telefono = re.sub(r"\D", "", f.get("telefono", ""))
        if telefono.startswith("591") and len(telefono) == 11:
            telefono = telefono[3:]
        if f.get("telefono") and not re.fullmatch(r"[67]\d{7}", telefono):
            campo.append("teléfono con %d dígitos: %s" % (len(telefono), f.get("telefono")))
        elif not telefono:
            campo.append("sin teléfono")
        mac_limpia, nota_mac, mac_campo = mac(f.get("mac"))
        if f.get("serie") or f.get("mac"):
            if nota_mac:
                (campo if mac_campo else obs).append(nota_mac)
        marca, modelo, notas_equipo = equipo(f.get("marca"), f.get("modelo"))
        obs += notas_equipo
        serie = "" if sin_dato(f.get("serie")) or (f.get("serie") or "").upper() == "PRUEBA" \
            else f["serie"].upper()
        if not serie:
            campo.append("ONU sin número de serie")
        modalidad_texto = clave(f.get("modalidad")) or "prepago"
        modalidad = MODALIDADES.get(modalidad_texto)
        if not modalidad:
            campo.append("modalidad desconocida «%s»: se toma prepago" % f.get("modalidad"))
            modalidad = "prepago"
        solicitud, activacion = fecha(f.get("fecha_solicitud")), fecha(f.get("fecha_activacion"))
        alta = activacion or solicitud
        if not activacion:
            campo.append("sin fecha de activación"
                         + (" (se usa la de solicitud)" if solicitud else ""))
        if solicitud and activacion and activacion < solicitud:
            campo.append("activación %s antes de la solicitud %s" % (
                f.get("fecha_activacion"), f.get("fecha_solicitud")))
        lat, lon = coordenada(f.get("latitud")), coordenada(f.get("longitud"))
        if lat is None or lon is None or not (LAT_BOLIVIA[0] < lat < LAT_BOLIVIA[1]
                                              and LON_BOLIVIA[0] < lon < LON_BOLIVIA[1]):
            if (f.get("latitud") or f.get("longitud")) and not (
                    sin_dato(f.get("latitud")) and sin_dato(f.get("longitud"))):
                campo.append("coordenadas inválidas: %s, %s" % (
                    f.get("latitud"), f.get("longitud")))
            else:
                campo.append("sin coordenadas")
            lat = lon = None
        if perfil and not mbps:
            obs.append("no se leyó la velocidad del perfil «%s»" % perfil)
        caja = "" if sin_dato(f.get("caja_nap")) else (f.get("caja_nap") or "").strip().upper()
        numero_puerto = None if sin_dato(f.get("puerto")) else puerto(f.get("puerto"))
        if caja and numero_puerto is None:
            campo.append("falta el PUERTO de la caja %s: no se asigna" % caja)
            caja = ""
        elif numero_puerto is not None and not caja:
            campo.append("falta la CAJA NAP del puerto %s: no se asigna" % numero_puerto)
            numero_puerto = None
        registros.append({
            "fila": f["fila"], "nombre": nombre_limpio, "ci": ci, "complemento": complemento,
            "expedido": expedido, "telefono": telefono, "barrio": barrio(f.get("barrio")),
            "direccion": "" if sin_dato(f.get("direccion")) else f.get("direccion", ""),
            "perfil": perfil, "mbps": mbps, "tv": tv, "precio": monto,
            "modalidad": modalidad, "usuario_pppoe": f.get("usuario_pppoe", ""),
            "ip": "" if sin_dato(f.get("ip")) else f.get("ip", ""),
            "marca": marca, "modelo": modelo, "serie": serie, "mac": mac_limpia,
            "fecha_solicitud": solicitud, "fecha_alta": alta, "latitud": lat, "longitud": lon,
            "caja_nap": caja, "puerto": numero_puerto,
            "observaciones": obs, "campo": campo, "error": "; ".join(error)})

    # Cruces entre filas. Un usuario PPPoE repetido es la misma conexión dos veces: solo vale la
    # primera fila. Una IP repetida no se le da a nadie más que al primero.
    primera_pppoe, primera_ip = {}, {}
    for r in registros:
        if r["error"]:
            continue
        usuario = r["usuario_pppoe"].lower()
        if usuario in primera_pppoe:
            r["error"] = "usuario PPPoE %s repetido en la planilla (fila %s)" % (
                r["usuario_pppoe"], primera_pppoe[usuario])
            continue
        primera_pppoe[usuario] = r["fila"]
        if r["ip"]:
            if r["ip"] in primera_ip:
                r["campo"].append("IP %s repetida en la planilla (fila %s): no se carga" % (
                    r["ip"], primera_ip[r["ip"]]))
                r["ip"] = ""
            else:
                primera_ip[r["ip"]] = r["fila"]

    # C.I. compartido por personas distintas y ONU repetidas.
    por_ci = collections.defaultdict(set)
    por_serie = collections.defaultdict(list)
    for r in registros:
        if r["ci"]:
            por_ci[r["ci"]].add(r["nombre"])
        if r["serie"]:
            por_serie[r["serie"]].append(r)
    for r in registros:
        if r["ci"] and len(por_ci[r["ci"]]) > 1:
            r["campo"].append("C.I. %s compartido con: %s" % (
                r["ci"], ", ".join(sorted(por_ci[r["ci"]] - {r["nombre"]}))))
        if r["serie"] and len(por_serie[r["serie"]]) > 1:
            otros = [o["nombre"] for o in por_serie[r["serie"]] if o is not r]
            r["campo"].append("misma ONU (serie %s) que: %s" % (r["serie"], ", ".join(otros)))
        for texto in r["campo"]:
            avisos.append({"fila": r["fila"], "cliente": r["nombre"], "que_revisar": texto})
        if r["error"]:
            avisos.append({"fila": r["fila"], "cliente": r["nombre"],
                           "que_revisar": "NO SE IMPORTA: " + r["error"]})
    avisos.sort(key=lambda a: a["fila"])
    return registros, avisos


def avisos_csv(avisos):
    """Avisos -> bytes de un CSV para abrir en Excel (UTF-8 con BOM, «;»)."""
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(["fila", "cliente", "que revisar"])
    for a in avisos:
        escritor.writerow([a["fila"], a["cliente"], a["que_revisar"]])
    return ("﻿" + salida.getvalue()).encode("utf-8")
