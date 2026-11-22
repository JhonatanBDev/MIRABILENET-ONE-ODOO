"""Cifrado de secretos de red (contraseñas de API y de PPPoE).

La clave maestra vive fuera de la base, en la variable de entorno
MIRABILENET_MASTER_KEY. Si se pierde, los secretos guardados no se recuperan.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

ENV_VAR = "MIRABILENET_MASTER_KEY"


class VaultError(Exception):
    pass


def _fernet():
    master = os.environ.get(ENV_VAR)
    if not master:
        raise VaultError(
            "Falta la clave maestra: defina la variable de entorno %s en el servidor." % ENV_VAR)
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(master.encode("utf-8")).digest()))


def encrypt(plain):
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt(token):
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise VaultError(
            "El secreto no se puede descifrar: la clave maestra no es la que lo cifró.")
