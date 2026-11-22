import secrets
from datetime import timedelta
from pathlib import Path

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from ..isp import addressing, enrollment, vault, wireguard
from ..isp.gateway import FakeRouterGateway, GatewayError, RealRouterGateway, RouterTarget

NETWORK_MANAGER = "mirabilenet_isp.group_mirabilenet_network_manager"
PARAM_DEFAULTS = {
    "mirabilenet.wg_mgmt_network": "10.250.0.0/16",
    "mirabilenet.wg_endpoint_host": "",
    "mirabilenet.wg_listen_port": "51820",
    "mirabilenet.wg_worker_ip": "10.250.0.20",
    "mirabilenet.wg_config_dir": "",
    "mirabilenet.platform_base_url": "",
    "mirabilenet.platform_ca_cn": "",
    "mirabilenet.platform_ca_pem_path": "",
    "mirabilenet.enrollment_ttl_minutes": "15",
    "mirabilenet.router_gateway": "real",
}
ENROLL_PATH = "/api/v1/network/router-enrollment/complete"
#: Lo que solo cambia el sistema (enrolamiento y diagnóstico), nunca un formulario.
SYSTEM_FIELDS = {
    "wg_ip", "wg_public_key", "wg_last_handshake", "wg_rx_bytes", "wg_tx_bytes", "identity",
    "serial", "board_name", "api_password_enc", "api_address_before", "state",
    "chk_handshake", "chk_ping", "chk_api", "chk_identity", "chk_version",
    "last_diagnosis", "diagnosis_detail",
}
HANDSHAKE_MAX_AGE = 180


class MirabilenetRouter(models.Model):
    """MikroTik administrado por la plataforma."""
    _name = "mirabilenet.router"
    _description = "MIRABILENET: router"
    _inherit = ["mirabilenet.region.scoped"]
    _order = "region_id, name"

    region_id = fields.Many2one("mirabilenet.region", string="Región", required=True,
                                ondelete="restrict", index=True)
    zone_id = fields.Many2one("mirabilenet.zone", string="Zona", ondelete="set null",
                              domain="[('region_id', '=', region_id)]")
    node_id = fields.Many2one("mirabilenet.node", string="Nodo", ondelete="set null",
                              domain="[('region_id', '=', region_id)]")
    name = fields.Char(string="Nombre", required=True)
    model = fields.Char(string="Modelo")
    equipment_type = fields.Selection(
        [("routerboard", "RouterBOARD"), ("chr", "CHR (virtual)"), ("x86", "x86")],
        string="Tipo de equipo", default="routerboard", required=True,
        help="CHR y x86 no tienen número de serie de RouterBOARD.")
    routeros_version = fields.Char(string="Versión de RouterOS")
    function = fields.Selection(
        [("pppoe", "Concentrador PPPoE"), ("camaras", "Acceso a cámaras"),
         ("ambos", "PPPoE y cámaras")], string="Función", default="pppoe", required=True)
    control_mode = fields.Selection(
        [("api", "API local de RouterOS"), ("radius", "RADIUS central")],
        string="Modo de control", default="api", required=True)

    wg_ip = fields.Char(string="IP de gestión (WireGuard)", readonly=True, copy=False,
                        index=True)
    wg_public_key = fields.Char(string="Llave pública", readonly=True, copy=False)
    wg_last_handshake = fields.Datetime(string="Último handshake", readonly=True)
    wg_rx_bytes = fields.Float(string="Bytes recibidos", digits=(20, 0), readonly=True)
    wg_tx_bytes = fields.Float(string="Bytes enviados", digits=(20, 0), readonly=True)

    identity = fields.Char(string="Identidad", readonly=True, copy=False)
    serial = fields.Char(string="Número de serie", readonly=True, copy=False)
    board_name = fields.Char(string="Placa", readonly=True, copy=False)

    api_user = fields.Char(string="Usuario de la API", default="mirabilenet_api",
                           required=True)
    api_password_enc = fields.Char(string="Contraseña de la API (cifrada)", copy=False,
                                   groups="base.group_system")
    has_credentials = fields.Boolean(string="Con credenciales",
                                     compute="_compute_has_credentials")
    api_port = fields.Integer(string="Puerto de la API", default=8728, required=True)
    api_address_before = fields.Char(
        string="Restricción previa de la API", readonly=True,
        help="Lista original de direcciones del servicio API, para poder restaurarla.")
    lan_networks = fields.Text(
        string="Redes LAN publicadas",
        help="Una por línea. Se publican hacia la plataforma por WireGuard.")

    state = fields.Selection(
        [("pendiente", "Pendiente de enrolamiento"), ("conectado", "Conectado"),
         ("degradado", "Degradado"), ("desconectado", "Desconectado"),
         ("retirado", "Retirado")],
        string="Estado", default="pendiente", required=True, readonly=True, index=True,
        copy=False)
    chk_handshake = fields.Boolean(string="Handshake", readonly=True, copy=False)
    chk_ping = fields.Boolean(string="Ping por el túnel", readonly=True, copy=False)
    chk_api = fields.Boolean(string="API accesible", readonly=True, copy=False)
    chk_identity = fields.Boolean(string="Identidad coincide", readonly=True, copy=False)
    chk_version = fields.Boolean(string="Versión coincide", readonly=True, copy=False)
    last_diagnosis = fields.Datetime(string="Último diagnóstico", readonly=True, copy=False)
    diagnosis_detail = fields.Json(string="Detalle del diagnóstico", readonly=True, copy=False)

    config_change_ids = fields.One2many("mirabilenet.router.config.change", "router_id",
                                        string="Cambios de configuración")
    service_ids = fields.One2many("mirabilenet.service", "router_id", string="Servicios")

    _name_uniq = models.Constraint("unique(name)", "Ya existe un router con ese nombre.")
    _wg_ip_uniq = models.Constraint("unique(wg_ip)", "Esa IP de gestión ya está en uso.")

    @api.depends("api_password_enc")
    def _compute_has_credentials(self):
        for router in self.sudo():
            router.has_credentials = bool(router.api_password_enc)

    @api.constrains("lan_networks")
    def _check_lan_networks(self):
        for router in self:
            try:
                addressing.parse_networks(router.lan_networks)
            except addressing.AddressingError as exc:
                raise ValidationError(str(exc))

    @api.constrains("region_id", "zone_id", "node_id")
    def _check_location(self):
        for router in self:
            if router.zone_id and router.zone_id.region_id != router.region_id:
                raise ValidationError(_("La zona no pertenece a la región del router."))
            if router.node_id and router.node_id.region_id != router.region_id:
                raise ValidationError(_("El nodo no pertenece a la región del router."))

    # ------------------------------------------------------------------
    @api.model
    def _param(self, name):
        key = "mirabilenet.%s" % name
        return self.env["ir.config_parameter"].sudo().get_param(key, PARAM_DEFAULTS[key])

    @api.model
    def _gateway(self):
        return FakeRouterGateway() if self._param("router_gateway") == "fake" \
            else RealRouterGateway()

    def _target(self):
        self.ensure_one()
        router = self.sudo()
        try:
            password = vault.decrypt(router.api_password_enc)
        except vault.VaultError as exc:
            raise GatewayError(str(exc))
        return RouterTarget(router.name, router.wg_ip, router.api_user, password,
                            router.api_port)

    def _lan_list(self):
        self.ensure_one()
        return addressing.parse_networks(self.lan_networks)

    def _allowed_ips_hub(self):
        """Lo que el concentrador acepta de este peer: su /32 y sus LAN publicadas."""
        self.ensure_one()
        return ["%s/32" % self.wg_ip] + self._lan_list()

    @api.model_create_multi
    def create(self, vals_list):
        Region = self.env["mirabilenet.region"]
        for vals in vals_list:
            if not self.env.su:
                for name in SYSTEM_FIELDS & set(vals):
                    vals.pop(name)
            region = Region.browse(vals.get("region_id"))
            if not region.exists():
                raise UserError(_("Indique la región del router."))
            if vals.get("wg_ip"):
                continue  # solo llega aquí bajo sudo: migración de datos
            # La IP de gestión la asigna la plataforma, no el operador.
            self.env.cr.execute(
                "SELECT id FROM mirabilenet_region WHERE id = %s FOR UPDATE", [region.id])
            self.flush_model()
            self.env.cr.execute("SELECT wg_ip FROM mirabilenet_router WHERE wg_ip IS NOT NULL")
            used = {row[0] for row in self.env.cr.fetchall()}
            used |= {v.get("wg_ip") for v in vals_list if v.get("wg_ip")}
            ip = addressing.next_management_ip(region.wg_region_id, used)
            if not ip:
                raise UserError(_(
                    "La región %s agotó su rango de gestión.", region.code))
            vals["wg_ip"] = ip
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and SYSTEM_FIELDS & set(vals):
            raise UserError(_(
                "Esos datos los fija el enrolamiento o el diagnóstico, no un formulario."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise UserError(_("Un router no se elimina: se retira."))
        return super().unlink()

    # ------------------------------------------------------------------
    # Estado: el handshake por sí solo no basta
    # ------------------------------------------------------------------
    def _evaluate_state(self):
        self.ensure_one()
        if self.state == "retirado":
            return "retirado"
        if all((self.chk_handshake, self.chk_ping, self.chk_api, self.chk_identity,
                self.chk_version)):
            return "conectado"
        if self.chk_handshake:
            return "degradado"
        return "desconectado" if self.wg_public_key else "pendiente"

    def _probe(self):
        """Los cinco chequeos: handshake, ping, API, identidad y versión."""
        gateway = self._gateway()
        config_dir = self._param("wg_config_dir")
        now = fields.Datetime.now()
        for router in self.sudo().filtered(lambda r: r.state != "retirado"):
            detail = {}
            handshake, rx, tx = (None, 0, 0)
            if router.wg_public_key:
                handshake, rx, tx = wireguard.peer_status(config_dir, router.wg_public_key)
            handshake = handshake.replace(tzinfo=None) if handshake else None
            vals = {
                "wg_last_handshake": handshake or False,
                "chk_handshake": bool(
                    handshake and (now - handshake).total_seconds() < HANDSHAKE_MAX_AGE),
                "wg_rx_bytes": rx, "wg_tx_bytes": tx,
                "chk_api": False, "chk_identity": False, "chk_version": False,
            }
            detail["handshake"] = handshake.isoformat() if handshake else None
            vals["chk_ping"] = bool(gateway.ping(router.wg_ip))
            detail["ping"] = vals["chk_ping"]
            if vals["chk_ping"] and router.api_password_enc:
                try:
                    info = gateway.identify(router._target())
                    vals["chk_api"] = True
                    detail["identidad_reportada"] = info.get("identity")
                    detail["version_reportada"] = info.get("version")
                    vals["chk_identity"] = bool(
                        router.identity and info.get("identity") == router.identity)
                    vals["chk_version"] = bool(
                        router.routeros_version
                        and info.get("version") == router.routeros_version)
                except GatewayError as exc:
                    detail["error_api"] = str(exc)
            previous = router.state
            vals.update(last_diagnosis=now, diagnosis_detail=detail)
            router.write(vals)
            router.state = router._evaluate_state()
            if previous != router.state:
                self.env["mirabilenet.audit.log"]._log(
                    "modificar", "Router %s: %s -> %s" % (router.name, previous, router.state),
                    record=router, region=router.region_id, payload=detail)
        return True

    def action_probe(self):
        self.check_access("read")
        self._probe()
        return True

    @api.model
    def _cron_probe(self):
        self.sudo().search([("state", "!=", "retirado")])._probe()

    # ------------------------------------------------------------------
    # Enrolamiento y baja
    # ------------------------------------------------------------------
    def _require_network_manager(self):
        if not self.env.su and not self.env.user.has_group(NETWORK_MANAGER):
            raise UserError(_("Su rol no administra routers."))

    def _read_setting_file(self, path, what):
        if not path or not Path(path).exists():
            raise UserError(_(
                "No se encuentra %(what)s (%(path)s). Sin eso el guion no puede enrolar de "
                "forma segura.", what=what, path=path or _("sin configurar")))
        return Path(path).read_text(encoding="utf-8").strip()

    def _generate_enrollment_script(self):
        """Código de un solo uso, contraseña de servicio y guion listo para pegar."""
        self.ensure_one()
        self._require_network_manager()
        if self.state == "retirado":
            raise UserError(_("El router está retirado; no se puede enrolar."))
        base_url = self._param("platform_base_url")
        endpoint = self._param("wg_endpoint_host")
        ca_cn = self._param("platform_ca_cn")
        if not (base_url and endpoint and ca_cn):
            raise UserError(_(
                "Falta configurar la dirección de la plataforma, el punto de entrada de "
                "WireGuard o el nombre de la CA (parámetros «mirabilenet.*»)."))
        hub_key = self._read_setting_file(
            str(Path(self._param("wg_config_dir") or ".") / "hub_public.key"),
            _("la llave pública del concentrador WireGuard"))
        ca_pem = self._read_setting_file(
            self._param("platform_ca_pem_path"), _("la CA de la plataforma"))
        ttl = int(self._param("enrollment_ttl_minutes"))
        mgmt = self._param("wg_mgmt_network")

        Token = self.env["mirabilenet.enrollment.token"].sudo()
        # Solo un código vigente a la vez.
        Token.search([("router_id", "=", self.id), ("state", "=", "vigente")]).write(
            {"state": "revocado"})
        api_password = secrets.token_urlsafe(24)
        token = Token.create({
            "token": secrets.token_urlsafe(32),
            "router_id": self.id,
            "expires_at": fields.Datetime.now() + timedelta(minutes=ttl),
            "user_id": self.env.user.id,
            "api_password_enc": vault.encrypt(api_password),
        })
        script = enrollment.render_enrollment({
            "ROUTER_NAME": self.name,
            "REGION_NAME": self.region_id.name,
            "GENERATED_AT": fields.Datetime.context_timestamp(
                self, fields.Datetime.now()).strftime("%Y-%m-%d %H:%M:%S %Z"),
            "TTL": ttl,
            "ROUTEROS_TARGET": self.routeros_version or "7.x",
            "WG_ROUTER_IP": self.wg_ip,
            "WG_SERVER_PUBLIC_KEY": hub_key,
            "WG_ENDPOINT": endpoint,
            "WG_SERVER_PORT": self._param("wg_listen_port"),
            "WG_ALLOWED_ADDRESSES": mgmt,
            "WG_MGMT_NETWORK": mgmt,
            "PLATFORM_WORKER_IP": self._param("wg_worker_ip"),
            "API_USER": self.api_user,
            "API_PORT": self.api_port,
            "GENERATED_API_PASSWORD": api_password,
            "ENROLLMENT_TOKEN": token.token,
            "ENROLL_URL": base_url.rstrip("/") + ENROLL_PATH,
            "ROUTER_LAN_NETWORKS_LIST": enrollment.routeros_list(self._lan_list()),
            "PLATFORM_CA_CN": ca_cn,
            "PLATFORM_CA_PEM": enrollment.pem_for_routeros(ca_pem),
            "WG_MTU": enrollment.suggested_mtu(),
        })
        self.env["mirabilenet.audit.log"]._log(
            "router_script", "Guion de enrolamiento generado para %s" % self.name,
            record=self, region=self.region_id,
            payload={"token_id": token.id, "expira": str(token.expires_at)})
        return script, token

    def _show_script(self, title, script, expires_at=False):
        wizard = self.env["mirabilenet.router.script.wizard"].create({
            "router_id": self.id, "script": script, "expires_at": expires_at})
        return {
            "type": "ir.actions.act_window", "name": title,
            "res_model": "mirabilenet.router.script.wizard", "res_id": wizard.id,
            "view_mode": "form", "target": "new",
        }

    def action_generate_enrollment(self):
        self.ensure_one()
        script, token = self._generate_enrollment_script()
        return self._show_script(_("Guion de enrolamiento"), script, token.expires_at)

    def _declare_peer(self):
        self.ensure_one()
        config_dir = self._param("wg_config_dir")
        if not config_dir:
            raise UserError(_("Falta configurar la carpeta de WireGuard."))
        return wireguard.declare_peer(
            config_dir, self.id, self.name, self.region_id.code, self.wg_public_key,
            self._allowed_ips_hub())

    def action_declare_peer(self):
        self._require_network_manager()
        for router in self.sudo():
            try:
                router._declare_peer()
            except (OSError, ValueError) as exc:
                raise UserError(_("No se pudo declarar el peer: %s", exc))
        return True

    def _offboard(self):
        """Revoca el peer en el servidor, retira el router y entrega el guion de baja."""
        self.ensure_one()
        self._require_network_manager()
        router = self.sudo()
        config_dir = self._param("wg_config_dir")
        if config_dir:
            wireguard.revoke_peer(config_dir, router.id)
        router.state = "retirado"
        self.env["mirabilenet.audit.log"]._log(
            "router_baja", "Guion de baja generado para %s" % router.name,
            record=router, region=router.region_id)
        return enrollment.render_offboard(router.name, router.api_user,
                                          router.api_address_before)

    def action_offboard(self):
        self.ensure_one()
        return self._show_script(_("Guion de baja"), self._offboard())
