"""Qué quiso decir el técnico cuando escribe en vez de apretar un botón (sin n8n)."""
import re
import unicodedata

ARREGLADO = ("arreglado", "arregle", "arreglé", "listo", "solucionado", "solucione", "ya quedo",
             "ya quedó", "quedo bien", "quedó bien", "funcionando", "ya funciona", "resuelto",
             "terminado", "ok ya", "reparado")
NO_RESUELTO = ("no se pudo", "no pude", "no se arreglo", "no se arregló", "no quedo",
               "no quedó", "imposible", "no hay acceso", "falta material", "no funciona aun",
               "no funciona aún", "sigue sin", "no resuelto")
EN_CAMINO = ("en camino", "voy para", "voy saliendo", "ya voy", "saliendo", "voy al",
             "voy a la", "llegando", "estoy yendo")


def _plano(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", texto.lower()).strip()


def accion(texto):
    """«arreglado», «no_resuelto», «en_camino» o None. Lo negativo se revisa primero:
    «no se pudo arreglar» no es «arreglado»."""
    plano = _plano(texto)
    if not plano:
        return None
    if any(_plano(f) in plano for f in NO_RESUELTO):
        return "no_resuelto"
    if any(_plano(f) in plano for f in EN_CAMINO):
        return "en_camino"
    if any(_plano(f) in plano for f in ARREGLADO):
        return "arreglado"
    return None
