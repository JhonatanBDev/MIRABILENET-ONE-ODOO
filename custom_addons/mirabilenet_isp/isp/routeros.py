"""Cliente minimo de la API binaria de RouterOS (§10.2 Etapa A).

Solo se usa a traves del tunel WireGuard: la API nunca queda publicada.
Implementa el protocolo de longitud variable documentado por MikroTik y el
login de RouterOS 6.43 en adelante (contrasena en claro sobre el tunel).

Nota: probado contra el simulador de sentencias incluido en las pruebas; su
comportamiento contra hardware real debe validarse en laboratorio antes de
usarlo en produccion.
"""

import logging
import socket

log = logging.getLogger(__name__)


class RouterOSError(Exception):
    pass


def _codificar_longitud(largo: int) -> bytes:
    if largo < 0x80:
        return bytes([largo])
    if largo < 0x4000:
        largo |= 0x8000
        return largo.to_bytes(2, "big")
    if largo < 0x200000:
        largo |= 0xC00000
        return largo.to_bytes(3, "big")
    if largo < 0x10000000:
        largo |= 0xE0000000
        return largo.to_bytes(4, "big")
    return b"\xf0" + largo.to_bytes(4, "big")


def _decodificar_longitud(sock) -> int:
    primero = _recibir_exacto(sock, 1)[0]
    if primero < 0x80:
        return primero
    if primero < 0xC0:
        resto = _recibir_exacto(sock, 1)
        return ((primero & ~0x80) << 8) + resto[0]
    if primero < 0xE0:
        resto = _recibir_exacto(sock, 2)
        return ((primero & ~0xC0) << 16) + int.from_bytes(resto, "big")
    if primero < 0xF0:
        resto = _recibir_exacto(sock, 3)
        return ((primero & ~0xE0) << 24) + int.from_bytes(resto, "big")
    resto = _recibir_exacto(sock, 4)
    return int.from_bytes(resto, "big")


def _recibir_exacto(sock, cantidad: int) -> bytes:
    datos = b""
    while len(datos) < cantidad:
        trozo = sock.recv(cantidad - len(datos))
        if not trozo:
            raise RouterOSError("Conexion cerrada por el router.")
        datos += trozo
    return datos


class RouterOSClient:
    """Conexion a la API de un MikroTik. Usar como context manager."""

    def __init__(self, host, usuario, contrasena, puerto=8728, timeout=8):
        self.host = host
        self.usuario = usuario
        self.contrasena = contrasena
        self.puerto = puerto
        self.timeout = timeout
        self.sock = None

    def __enter__(self):
        self.conectar()
        return self

    def __exit__(self, *exc):
        self.cerrar()

    def conectar(self):
        self.sock = socket.create_connection(
            (self.host, self.puerto), timeout=self.timeout
        )
        self.sock.settimeout(self.timeout)
        respuesta = self.ejecutar(
            "/login", {"name": self.usuario, "password": self.contrasena}
        )
        if any(s[0] == "!trap" for s in respuesta):
            raise RouterOSError("Credenciales rechazadas por el router.")
        return self

    def cerrar(self):
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None

    # --- protocolo ---
    def _enviar_palabra(self, palabra: str):
        crudo = palabra.encode("utf-8")
        self.sock.sendall(_codificar_longitud(len(crudo)) + crudo)

    def _enviar_sentencia(self, palabras):
        for palabra in palabras:
            self._enviar_palabra(palabra)
        self._enviar_palabra("")

    def _leer_sentencia(self):
        palabras = []
        while True:
            largo = _decodificar_longitud(self.sock)
            if largo == 0:
                break
            palabras.append(_recibir_exacto(self.sock, largo).decode("utf-8", "replace"))
        return palabras

    def ejecutar(self, comando, atributos=None, consultas=None):
        """Envia un comando y devuelve la lista de sentencias de respuesta."""
        palabras = [comando]
        for clave, valor in (atributos or {}).items():
            palabras.append(f"={clave}={valor}")
        for consulta in consultas or []:
            palabras.append(f"?{consulta}")
        self._enviar_sentencia(palabras)

        respuestas = []
        while True:
            sentencia = self._leer_sentencia()
            if not sentencia:
                continue
            tipo = sentencia[0]
            datos = {}
            for palabra in sentencia[1:]:
                if palabra.startswith("="):
                    clave, _, valor = palabra[1:].partition("=")
                    datos[clave] = valor
            respuestas.append((tipo, datos))
            if tipo in ("!done", "!fatal"):
                break
            if tipo == "!trap":
                continue
        return respuestas

    def consultar(self, comando, consultas=None):
        """Devuelve solo las filas de datos (`!re`) de un print."""
        return [
            datos
            for tipo, datos in self.ejecutar(comando, consultas=consultas)
            if tipo == "!re"
        ]

    # --- operaciones de alto nivel usadas por la plataforma ---
    def identidad(self):
        filas = self.consultar("/system/identity/print")
        return filas[0].get("name", "") if filas else ""

    def version(self):
        filas = self.consultar("/system/resource/print")
        return filas[0].get("version", "") if filas else ""

    def recursos(self):
        filas = self.consultar("/system/resource/print")
        return filas[0] if filas else {}

    def buscar_secret(self, username):
        filas = self.consultar("/ppp/secret/print", consultas=[f"name={username}"])
        return filas[0] if filas else None

    def actualizar_secret(self, secret_id, **campos):
        atributos = {".id": secret_id}
        atributos.update({k.replace("_", "-"): v for k, v in campos.items()})
        return self.ejecutar("/ppp/secret/set", atributos)

    def habilitar_secret(self, secret_id, habilitado: bool):
        return self.ejecutar(
            "/ppp/secret/set",
            {".id": secret_id, "disabled": "no" if habilitado else "yes"},
        )

    def desconectar_sesion(self, username):
        for sesion in self.consultar("/ppp/active/print", consultas=[f"name={username}"]):
            self.ejecutar("/ppp/active/remove", {".id": sesion.get(".id", "")})
