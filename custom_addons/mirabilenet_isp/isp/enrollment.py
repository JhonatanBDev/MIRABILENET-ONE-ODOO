"""Guiones RouterOS de enrolamiento y de baja.

Las dos plantillas son las del sistema anterior (plantilla v1.1), copiadas sin
cambios: su contenido está cubierto por pruebas. Si se toca una, hay que
actualizar las pruebas a conciencia y validarla en laboratorio.

Este archivo no importa Odoo.
"""

ENROLLMENT_TEMPLATE = r"""# =============================================================
# MIRABILENET ONE - Enrolamiento seguro de router  (plantilla v1.1)
# Router:   __ROUTER_NAME__
# Region:   __REGION_NAME__
# Generado: __GENERATED_AT__   Token de un solo uso, valido __TTL__ min
# RouterOS objetivo: __ROUTEROS_TARGET__
# =============================================================

# -------------------------------------------------------------
# IMPORTANTE: todo el script va dentro de UNAS LLAVES, y no es
# decoracion. La consola de RouterOS ejecuta cada linea pegada como
# un script aparte: sin las llaves, cada :local se pierde antes de
# la linea siguiente (las variables llegan vacias) y, peor, un
# :error de los guardias de seguridad solo aborta su propia linea
# mientras el resto se sigue ejecutando.
#
# Peguelo COMPLETO de una sola vez. La consola espera a que cierre
# la llave antes de ejecutar nada.
#
# Si su terminal corta el pegado (el script es largo por el
# certificado), guardelo como archivo .rsc, subalo al router y use:
#     /import file=mnone-enrolamiento.rsc
# -------------------------------------------------------------

{

    :local wgName      "wg-mirabilenet"
    :local wgAddress   "__WG_ROUTER_IP__/32"
    :local wgServerKey "__WG_SERVER_PUBLIC_KEY__"
    :local wgEndpoint  "__WG_ENDPOINT__"
    :local wgPort      __WG_SERVER_PORT__
    :local wgAllowed   "__WG_ALLOWED_ADDRESSES__"
    :local mgmtNet     "__WG_MGMT_NETWORK__"
    :local workerIp    "__PLATFORM_WORKER_IP__"
    :local apiUser     "__API_USER__"
    :local apiPassword "__GENERATED_API_PASSWORD__"
    :local enrollToken "__ENROLLMENT_TOKEN__"
    :local enrollUrl   "__ENROLL_URL__"
    :local lanNets     __ROUTER_LAN_NETWORKS_LIST__
    :local tag         "MIRABILENET ONE"

    # -------------------------------------------------------------
    # BLOQUE 1 - Guardia: no ejecutar a traves del propio tunel
    # -------------------------------------------------------------
    :local viaTunnel false
    :foreach s in=[/user/active find] do={
        :local a [:toip [/user/active get $s address]]
        :if ([:typeof $a] = "ip") do={
            :if ($a in __WG_MGMT_NETWORK__) do={ :set viaTunnel true }
        }
    }
    :if ($viaTunnel) do={
        :log error "$tag: sesion iniciada por la red de gestion. Ejecute por LAN o consola."
        :error "MIRABILENET ONE: ejecucion cancelada por seguridad."
    }

    # -------------------------------------------------------------
    # BLOQUE 2 - Respaldo previo obligatorio
    # -------------------------------------------------------------
    :local stamp ([:pick [/system/clock get date] 0 11] . "-" . \
                  [:pick [/system/clock get time] 0 2] . [:pick [/system/clock get time] 3 5])
    :do {
        /system/backup save name=("mnone-pre-enroll-" . $stamp) dont-encrypt=yes
        /export file=("mnone-pre-enroll-" . $stamp)
    } on-error={
        :log error "$tag: no se pudo crear el respaldo previo."
        :error "MIRABILENET ONE: sin respaldo no se continua."
    }

    # -------------------------------------------------------------
    # BLOQUE 3 - Certificado de la CA de la plataforma
    # Sin CA valida no se envia el token: se prefiere fallar.
    # -------------------------------------------------------------
    :if ([:len [/certificate find where common-name="__PLATFORM_CA_CN__"]] = 0) do={
        :do { /file remove [find where name="mnone-ca.pem"] } on-error={}
        :do {
            /file add name="mnone-ca.pem" contents="__PLATFORM_CA_PEM__"
            :delay 1s
            /certificate import file-name="mnone-ca.pem" passphrase=""
        } on-error={
            :log error "$tag: no se pudo importar la CA. Importela manualmente y reintente."
            :error "MIRABILENET ONE: CA ausente."
        }
    }
    :if ([:len [/certificate find where common-name="__PLATFORM_CA_CN__"]] = 0) do={
        :error "MIRABILENET ONE: la CA no quedo instalada."
    }

    # -------------------------------------------------------------
    # BLOQUE 4 - Interfaz WireGuard
    # -------------------------------------------------------------
    :if ([:len [/interface/wireguard find where name=$wgName]] > 0) do={
        /ip/address remove [find where interface=$wgName]
        /interface/wireguard remove [find where name=$wgName]
    }
    /interface/wireguard add name=$wgName mtu=__WG_MTU__ comment="$tag - Gestion privada"
    /ip/address add address=$wgAddress interface=$wgName comment="$tag"

    # -------------------------------------------------------------
    # BLOQUE 5 - Peer de la VPS (nunca 0.0.0.0/0)
    # -------------------------------------------------------------
    /interface/wireguard/peers add \
        interface=$wgName \
        public-key=$wgServerKey \
        endpoint-address=$wgEndpoint \
        endpoint-port=$wgPort \
        allowed-address=$wgAllowed \
        persistent-keepalive=25 \
        comment="$tag - VPS"

    # -------------------------------------------------------------
    # BLOQUE 5b - Ruta de vuelta hacia la red de gestion
    # La interfaz lleva una /32: es una punto a punto, asi que no deja
    # ninguna ruta de subred. Y RouterOS 7 NO crea rutas a partir del
    # allowed-address del peer. Sin esta ruta el handshake se establece
    # igual, pero la respuesta del router hacia la VPS no encuentra el
    # tunel y sale por la ruta por defecto, donde se pierde: el panel ve
    # el equipo como Degradado con solo el handshake en verde.
    # -------------------------------------------------------------
    /ip/route remove [find where comment~"^MIRABILENET ONE: gestion"]
    /ip/route add dst-address=$mgmtNet gateway=$wgName \
        comment="MIRABILENET ONE: gestion"

    # -------------------------------------------------------------
    # BLOQUE 6 - Firewall de gestion  (CORRECCION CRITICA)
    # Sin estas reglas el handshake funciona pero la VPS no alcanza
    # el router: la cadena input descarta lo que no viene de LAN.
    # -------------------------------------------------------------
    /ip/firewall/filter remove [find where comment~"^MIRABILENET ONE: gestion"]

    :local rIcmp [/ip/firewall/filter add chain=input action=accept \
        in-interface=$wgName src-address=$mgmtNet protocol=icmp \
        comment="MIRABILENET ONE: gestion ICMP por WireGuard"]
    /ip/firewall/filter move $rIcmp destination=0

    :local rApi [/ip/firewall/filter add chain=input action=accept \
        in-interface=$wgName src-address=("$workerIp/32") \
        protocol=tcp dst-port=__API_PORT__ \
        comment="MIRABILENET ONE: gestion API desde worker"]
    /ip/firewall/filter move $rApi destination=0

    :local rAdm [/ip/firewall/filter add chain=input action=accept \
        in-interface=$wgName src-address=$mgmtNet \
        protocol=tcp dst-port=22,8291 \
        comment="MIRABILENET ONE: gestion SSH y Winbox por WireGuard"]
    /ip/firewall/filter move $rAdm destination=0

    # -------------------------------------------------------------
    # BLOQUE 7 - Redes LAN publicadas hacia la plataforma
    # -------------------------------------------------------------
    /ip/firewall/filter remove [find where comment~"^MIRABILENET ONE: LAN publicada"]
    :foreach lan in=$lanNets do={
        :do {
            :local rf [/ip/firewall/filter add chain=forward action=accept \
                in-interface=$wgName src-address=$mgmtNet dst-address=$lan \
                comment=("MIRABILENET ONE: LAN publicada " . $lan)]
            /ip/firewall/filter move $rf destination=0
        } on-error={
            :log warning "$tag: no se pudo publicar la red $lan."
        }
    }

    # -------------------------------------------------------------
    # BLOQUE 8 - Cuenta de servicio con privilegios limitados
    # -------------------------------------------------------------
    :if ([:len [/user/group find where name="mirabilenet-platform"]] = 0) do={
        /user/group add name="mirabilenet-platform" \
            policy=read,write,test,api,rest-api \
            comment="$tag API"
    }
    :if ([:len [/user find where name=$apiUser]] > 0) do={
        /user remove [find where name=$apiUser]
    }
    /user add name=$apiUser password=$apiPassword group="mirabilenet-platform" \
        comment="Cuenta de servicio $tag"

    # -------------------------------------------------------------
    # BLOQUE 9 - API: agregar el worker SIN borrar lo existente
    # -------------------------------------------------------------
    # `address` espera una cadena separada por comas, no una lista: si se le
    # pasa el arreglo tal cual, RouterOS responde "invalid value for argument
    # address" y el worker se queda sin acceso a la API.
    :local apiList [/ip/service get [find where name="api"] address]
    :local apiBefore ""
    :local found false
    :foreach a in=$apiList do={
        :local t [:tostr $a]
        :if ($apiBefore = "") do={ :set apiBefore $t } else={ :set apiBefore ($apiBefore . "," . $t) }
        :if ($t = ($workerIp . "/32")) do={ :set found true }
    }
    :local apiNuevo $apiBefore
    :if (!$found) do={
        :if ($apiNuevo = "") do={
            :set apiNuevo ($workerIp . "/32")
        } else={
            :set apiNuevo ($apiNuevo . "," . $workerIp . "/32")
        }
    }
    /ip/service set [find where name="api"] address=$apiNuevo disabled=no

    # -------------------------------------------------------------
    # BLOQUE 10 - Identidad del equipo, tolerante a no-RouterBOARD
    # -------------------------------------------------------------
    :local identity [/system/identity get name]
    :local version  [/system/resource get version]
    :local board    "N/D"
    :local serial   "N/D"
    :do { :set board [/system/resource get board-name] } on-error={}
    :do { :set serial [/system/routerboard get serial-number] } on-error={
        :set serial "no-routerboard"
    }
    :local pubKey [/interface/wireguard get [find where name=$wgName] public-key]

    # -------------------------------------------------------------
    # BLOQUE 11 - Reporte con certificado validado y respuesta verificada
    # -------------------------------------------------------------
    :local payload ("{\"token\":\"" . $enrollToken . \
        "\",\"public_key\":\"" . $pubKey . \
        "\",\"identity\":\"" . $identity . \
        "\",\"board\":\"" . $board . \
        "\",\"serial\":\"" . $serial . \
        "\",\"version\":\"" . $version . \
        "\",\"api_address_before\":\"" . $apiBefore . \
        "\",\"backup_name\":\"mnone-pre-enroll-" . $stamp . "\"}")

    :local ok false
    :do {
        :local resp [/tool/fetch url=$enrollUrl http-method=post \
            http-header-field="Content-Type: application/json" \
            http-data=$payload \
            check-certificate=yes-without-crl \
            output=user as-value]
        :if (($resp->"status") = "finished") do={ :set ok true }
    } on-error={ :set ok false }

    :if ($ok) do={
        :log info "$tag: enrolamiento enviado. Verifique el diagnostico en el panel."
        :put "MIRABILENET ONE: enrolamiento enviado correctamente."
    } else={
        :log error "$tag: fallo el envio del enrolamiento."
        :put "MIRABILENET ONE: no se pudo contactar al panel."
        :put "Use Enrolamiento manual y pegue esta llave publica:"
        :put $pubKey
    }

}
"""

OFFBOARD_TEMPLATE = r"""# =============================================================
# MIRABILENET ONE - Baja segura del router __ROUTER_NAME__
# El peer ya fue revocado en la VPS antes de generar este script.
#
# Como el de enrolamiento, va dentro de unas llaves: la consola de
# RouterOS ejecuta cada linea pegada por separado y los :local no
# sobreviven de una a otra. Peguelo completo de una sola vez.
# =============================================================

{

    :local wgName "wg-mirabilenet"
    :local tag    "MIRABILENET ONE"

    /system/backup save name="mnone-pre-offboard" dont-encrypt=yes
    /export file="mnone-pre-offboard"

    /ip/firewall/filter remove [find where comment~"^MIRABILENET ONE:"]
    /ip/firewall/nat    remove [find where comment~"^MIRABILENET ONE:"]
    /ip/route           remove [find where comment~"^MIRABILENET ONE"]
    /ip/address         remove [find where comment~"^MIRABILENET ONE"]
    /interface/wireguard remove [find where name=$wgName]
    /user remove [find where name="__API_USER__"]
    /user/group remove [find where name="mirabilenet-platform"]

    # Restaurar la lista original de direcciones del servicio API
    /ip/service set [find where name="api"] address=__API_ADDRESS_BEFORE__

    :log info "$tag: router retirado de la plataforma."

}
"""

ENROLLMENT_KEYS = (
    "ROUTER_NAME", "REGION_NAME", "GENERATED_AT", "TTL", "ROUTEROS_TARGET",
    "WG_ROUTER_IP", "WG_SERVER_PUBLIC_KEY", "WG_ENDPOINT", "WG_SERVER_PORT",
    "WG_ALLOWED_ADDRESSES", "WG_MGMT_NETWORK", "PLATFORM_WORKER_IP", "API_USER",
    "API_PORT", "GENERATED_API_PASSWORD", "ENROLLMENT_TOKEN", "ENROLL_URL",
    "ROUTER_LAN_NETWORKS_LIST", "PLATFORM_CA_CN", "PLATFORM_CA_PEM", "WG_MTU",
)


def routeros_list(values):
    """Lista de Python -> arreglo literal de RouterOS."""
    if not values:
        return "{}"
    return "{" + ";".join('"%s"' % v for v in values) + "}"


def pem_for_routeros(pem):
    """La CA en una sola cadena, con los saltos escapados."""
    return pem.strip().replace("\n", "\\n")


def suggested_mtu():
    """1412 cubre un enlace PPPoE (1492 - 60)."""
    return 1412


def render_enrollment(values):
    missing = [key for key in ENROLLMENT_KEYS if key not in values]
    if missing:
        raise ValueError("Faltan datos para el guion: %s" % ", ".join(missing))
    script = ENROLLMENT_TEMPLATE
    for key in ENROLLMENT_KEYS:
        script = script.replace("__%s__" % key, str(values[key]))
    return script


def render_offboard(router_name, api_user, api_address_before):
    script = OFFBOARD_TEMPLATE
    script = script.replace("__ROUTER_NAME__", router_name)
    script = script.replace("__API_USER__", api_user)
    return script.replace("__API_ADDRESS_BEFORE__", api_address_before or '""')
