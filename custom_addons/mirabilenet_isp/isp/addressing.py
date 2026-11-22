"""Direccionamiento por región.

    Subred de un sitio:   10.<64 + ID_REGION>.<ID_SITIO>.0/24   (sobre 10.64.0.0/10)
    Gestión WireGuard:    10.250.<ID_REGION * 10>.<host>/32

ID_REGION va de 0 a 63 e ID_SITIO de 1 a 254.
"""
import ipaddress

SITE_MIN = 1
SITE_MAX = 254
REGION_MAX = 63
QUARANTINE_DAYS = 30
DEFAULT_SUPERNET = "10.64.0.0/10"


class AddressingError(ValueError):
    pass


def site_cidr(region_wg_id, site_id):
    if not 0 <= region_wg_id <= REGION_MAX:
        raise AddressingError("El id de región debe estar entre 0 y %d." % REGION_MAX)
    if not SITE_MIN <= site_id <= SITE_MAX:
        raise AddressingError(
            "El id de sitio debe estar entre %d y %d." % (SITE_MIN, SITE_MAX))
    return "10.%d.%d.0/24" % (64 + region_wg_id, site_id)


def within_supernet(cidr, supernet=DEFAULT_SUPERNET):
    return ipaddress.ip_network(cidr).subnet_of(ipaddress.ip_network(supernet))


def next_free_site(used):
    """Primer id de sitio libre, o None si la región se agotó."""
    used = set(used)
    return next((n for n in range(SITE_MIN, SITE_MAX + 1) if n not in used), None)


def gateway_of(cidr):
    return str(ipaddress.ip_network(cidr).network_address + 1)


def next_management_ip(region_wg_id, used):
    """Siguiente /32 libre de la red de gestión de la región."""
    used = set(used)
    for host in range(2, 255):
        candidate = "10.250.%d.%d" % (region_wg_id * 10, host)
        if candidate not in used:
            return candidate
    return None


def parse_networks(text):
    """Redes escritas una por línea -> lista normalizada. Rechaza lo que no es una red."""
    networks = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            networks.append(str(ipaddress.ip_network(line, strict=True)))
        except ValueError:
            raise AddressingError("«%s» no es una red válida (ejemplo: 192.168.10.0/24)." % line)
    return networks


def netmap_rules(site_id, region_name, real_network, virtual_cidr,
                 interface="wg-mirabilenet"):
    """Par de reglas netmap para un sitio que conserva su red original."""
    return (
        "# Sitio {site} de {region}: {real} real <-> {virtual} virtual\n"
        "/ip/firewall/nat add chain=dstnat action=netmap \\\n"
        "    in-interface={wg} dst-address={virtual} \\\n"
        "    to-addresses={real} \\\n"
        "    comment=\"MIRABILENET ONE: netmap sitio {site} entrada\"\n"
        "\n"
        "/ip/firewall/nat add chain=srcnat action=netmap \\\n"
        "    out-interface={wg} src-address={real} \\\n"
        "    to-addresses={virtual} \\\n"
        "    comment=\"MIRABILENET ONE: netmap sitio {site} salida\"\n"
    ).format(site=site_id, region=region_name, real=real_network, virtual=virtual_cidr,
             wg=interface)
