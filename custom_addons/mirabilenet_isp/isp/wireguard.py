"""Peers del concentrador WireGuard.

No se toca la interfaz del servidor: se escribe la intención en
<carpeta>/peers/ y un servicio del propio servidor la aplica. Así el proceso de
Odoo no necesita privilegios de red y cada cambio queda en un archivo.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _peer_file(config_dir, router_id):
    folder = Path(config_dir) / "peers"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / ("router-%s.json" % router_id)


def _now():
    return datetime.now(timezone.utc).isoformat()


def declare_peer(config_dir, router_id, name, region_code, public_key, allowed_ips):
    """AllowedIPs = la /32 de gestión más las LAN publicadas. Nunca 0.0.0.0/0."""
    if not public_key:
        raise ValueError("El router todavía no informó su llave pública.")
    if any(ip.startswith("0.0.0.0/") for ip in allowed_ips):
        raise ValueError("Un peer nunca lleva 0.0.0.0/0.")
    data = {
        "router_id": router_id, "nombre": name, "region": region_code,
        "public_key": public_key, "allowed_ips": list(allowed_ips),
        "revocado": False, "actualizado": _now(),
    }
    path = _peer_file(config_dir, router_id)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return data


def revoke_peer(config_dir, router_id):
    path = _peer_file(config_dir, router_id)
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(revocado=True, actualizado=_now())
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return True


def hub_status(config_dir):
    """Estado real de la interfaz, tal como lo deja el servicio del servidor."""
    empty = {"peers": {}, "actualizado": None, "disponible": False}
    if not config_dir:
        return empty
    path = Path(config_dir) / "status.json"
    if not path.exists():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty
    data["disponible"] = True
    return data


def peer_status(config_dir, public_key):
    """(último handshake o None, bytes recibidos, bytes enviados)."""
    entry = hub_status(config_dir).get("peers", {}).get(public_key) or {}
    stamp = int(entry.get("latest_handshake") or 0)
    handshake = datetime.fromtimestamp(stamp, tz=timezone.utc) if stamp else None
    return handshake, int(entry.get("rx") or 0), int(entry.get("tx") or 0)
