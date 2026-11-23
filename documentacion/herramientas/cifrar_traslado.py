"""Cifra o descifra una carpeta con contraseña para llevarla a otra PC sin USB.

Sirve para lo que tiene secretos (por ejemplo el volumen de n8n con sus credenciales):
el archivo .cifrado se puede subir a la nube o a un repositorio privado, porque sin la
contraseña no se puede leer. La contraseña se escribe en la terminal (no queda en la
pantalla ni en el historial): no la pegue en ningún chat.

Usa el Python del entorno de Odoo (trae la librería cryptography). En PowerShell:

  Cifrar (en la PC de origen):
    env\\Scripts\\python.exe documentacion\\herramientas\\cifrar_traslado.py cifrar <carpeta>
    -> crea <carpeta>.zip.cifrado al lado de la carpeta

  Descifrar (en la otra PC):
    env\\Scripts\\python.exe documentacion\\herramientas\\cifrar_traslado.py descifrar <archivo.zip.cifrado>
    -> crea la carpeta al lado del archivo

Cifrado: AES (Fernet) con clave derivada de la contraseña por scrypt (sal aleatoria).
"""
import base64
import getpass
import io
import os
import sys
import zipfile

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIA = b"MNCIF1"
LARGO_SAL = 16


def _clave(contrasena, sal):
    kdf = Scrypt(salt=sal, length=32, n=2 ** 15, r=8, p=1)
    return base64.urlsafe_b64encode(kdf.derive(contrasena.encode("utf-8")))


def cifrar(carpeta):
    carpeta = os.path.abspath(carpeta.rstrip("\\/"))
    if not os.path.isdir(carpeta):
        sys.exit("No existe la carpeta %s" % carpeta)
    contrasena = getpass.getpass("Contraseña nueva (mínimo 12 caracteres): ")
    if len(contrasena) < 12:
        sys.exit("La contraseña es muy corta.")
    if getpass.getpass("Repítala: ") != contrasena:
        sys.exit("Las contraseñas no coinciden.")
    memoria = io.BytesIO()
    base = os.path.basename(carpeta)
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as zf:
        for raiz, _dirs, archivos in os.walk(carpeta):
            for nombre in archivos:
                ruta = os.path.join(raiz, nombre)
                zf.write(ruta, os.path.join(base, os.path.relpath(ruta, carpeta)))
    sal = os.urandom(LARGO_SAL)
    datos = Fernet(_clave(contrasena, sal)).encrypt(memoria.getvalue())
    destino = carpeta + ".zip.cifrado"
    with open(destino, "wb") as f:
        f.write(MAGIA + sal + datos)
    print("Listo: %s (%d bytes)" % (destino, os.path.getsize(destino)))


def descifrar(archivo):
    archivo = os.path.abspath(archivo)
    with open(archivo, "rb") as f:
        contenido = f.read()
    if not contenido.startswith(MAGIA):
        sys.exit("El archivo no fue hecho con este script.")
    sal = contenido[len(MAGIA):len(MAGIA) + LARGO_SAL]
    datos = contenido[len(MAGIA) + LARGO_SAL:]
    contrasena = getpass.getpass("Contraseña: ")
    try:
        zip_bytes = Fernet(_clave(contrasena, sal)).decrypt(datos)
    except InvalidToken:
        sys.exit("Contraseña incorrecta o archivo dañado.")
    destino = os.path.dirname(archivo)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        zf.extractall(destino)
        print("Listo: carpeta %s" % os.path.join(destino, zf.namelist()[0].split("/")[0].split("\\")[0]))


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("cifrar", "descifrar"):
        sys.exit(__doc__)
    (cifrar if sys.argv[1] == "cifrar" else descifrar)(sys.argv[2])
