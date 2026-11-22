"""SiatTokenVault: cifrado en reposo de tokens delegados, CUIS y CUFD.

La clave maestra vive FUERA de la base de datos (variable de entorno o
archivo de configuración del servidor). Sin clave no se guarda ni se lee nada.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from . import errors


class Vault:
    def __init__(self, master_key):
        if not master_key:
            raise errors.SiatError(
                errors.TOKEN,
                "No hay clave maestra de cifrado configurada en el servidor "
                "(MIRA_SIAT_MASTER_KEY).")
        digest = hashlib.sha256(master_key.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, plaintext):
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext):
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken:
            raise errors.SiatError(
                errors.TOKEN,
                "No se pudo descifrar el secreto: la clave maestra del servidor "
                "no es la que se usó para guardarlo.")


def fingerprint(secret):
    """Huella corta para identificar un secreto sin revelarlo."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]
