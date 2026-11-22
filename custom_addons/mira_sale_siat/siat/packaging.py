"""Compresión, huella y empaquetado de archivos fiscales."""

import gzip
import hashlib
import io
import tarfile


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def gzip_bytes(data):
    """GZIP determinista (mtime=0): el mismo XML produce siempre el mismo hash."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(data)
    return buf.getvalue()


def tar_gz(files):
    """Empaqueta [(nombre, bytes), ...] en un TAR comprimido con GZIP."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for name, data in files:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = 0
            tar.addfile(info, io.BytesIO(data))
    return gzip_bytes(raw.getvalue())


def chunked(items, size):
    """Parte una lista en bloques de `size` (tamaño de paquete parametrizable)."""
    if size < 1:
        raise ValueError("El tamaño de paquete debe ser al menos 1.")
    return [items[i:i + size] for i in range(0, len(items), size)]
