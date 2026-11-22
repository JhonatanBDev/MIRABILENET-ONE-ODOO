import json
import os
import re
import shutil
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

from ..isp import addressing, enrollment, vault, wireguard
from ..isp.gateway import FakeRouterGateway


@tagged("mirabilenet", "post_install", "-at_install")
class TestAddressing(TransactionCase):
    """Reglas puras de direccionamiento: no tocan la base."""

    def test_site_cidr(self):
        self.assertEqual(addressing.site_cidr(0, 1), "10.64.1.0/24")
        self.assertEqual(addressing.site_cidr(63, 254), "10.127.254.0/24")
        for region, site in ((64, 1), (-1, 1), (0, 0), (0, 255)):
            with self.assertRaises(addressing.AddressingError):
                addressing.site_cidr(region, site)

    def test_no_overlap_anywhere(self):
        seen = set()
        for region in range(0, 64):
            for site in (1, 2, 127, 254):
                cidr = addressing.site_cidr(region, site)
                self.assertNotIn(cidr, seen)
                self.assertTrue(addressing.within_supernet(cidr))
                seen.add(cidr)

    def test_next_free_site(self):
        self.assertEqual(addressing.next_free_site([]), 1)
        self.assertEqual(addressing.next_free_site([1, 2, 4]), 3)
        self.assertIsNone(addressing.next_free_site(range(1, 255)))

    def test_management_ip(self):
        self.assertEqual(addressing.next_management_ip(3, []), "10.250.30.2")
        self.assertEqual(addressing.next_management_ip(3, ["10.250.30.2"]), "10.250.30.3")

    def test_parse_networks(self):
        self.assertEqual(addressing.parse_networks("192.168.1.0/24\n\n10.0.0.0/8 "),
                         ["192.168.1.0/24", "10.0.0.0/8"])
        for bad in ("hola", "192.168.1.5/24", "0.0.0.0/33"):
            with self.assertRaises(addressing.AddressingError):
                addressing.parse_networks(bad)

    def test_vault(self):
        with patch.dict(os.environ, {vault.ENV_VAR: "clave-de-prueba"}):
            secret = vault.encrypt("s3creta")
            self.assertNotIn("s3creta", secret)
            self.assertEqual(vault.decrypt(secret), "s3creta")
        with patch.dict(os.environ, {vault.ENV_VAR: "otra-clave"}):
            with self.assertRaises(vault.VaultError):
                vault.decrypt(secret)
        with patch.dict(os.environ, clear=True):
            with self.assertRaises(vault.VaultError):
                vault.encrypt("x")

    def test_peer_never_default_route(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        with self.assertRaises(ValueError):
            wireguard.declare_peer(folder, 1, "r", "N", "llave", ["0.0.0.0/0"])
        with self.assertRaises(ValueError):
            wireguard.declare_peer(folder, 1, "r", "N", "", ["10.250.10.2/32"])


class NetworkCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.startClassPatcher(patch.dict(os.environ, {vault.ENV_VAR: "clave-de-prueba"}))
        FakeRouterGateway.reset()
        cls.wg_dir = tempfile.mkdtemp()
        cls.addClassCleanup(shutil.rmtree, cls.wg_dir, True)
        Path(cls.wg_dir, "hub_public.key").write_text("LLAVE-PUBLICA-DEL-HUB=")
        cls.ca_path = str(Path(cls.wg_dir, "ca.pem"))
        Path(cls.ca_path).write_text(
            "-----BEGIN CERTIFICATE-----\nAAAA\nBBBB\n-----END CERTIFICATE-----\n")
        Param = cls.env["ir.config_parameter"]
        for key, value in {
            "router_gateway": "fake", "wg_config_dir": cls.wg_dir,
            "platform_base_url": "https://203.0.113.10/", "wg_endpoint_host": "vpn.example",
            "platform_ca_cn": "CA de prueba", "platform_ca_pem_path": cls.ca_path,
        }.items():
            Param.set_param("mirabilenet.%s" % key, value)

        Region = cls.env["mirabilenet.region"]
        cls.norte = Region.create({"code": "T-N", "name": "Norte", "wg_region_id": 1})
        cls.sur = Region.create({"code": "T-S", "name": "Sur", "wg_region_id": 2})
        zone = cls.env["mirabilenet.zone"].create(
            {"region_id": cls.norte.id, "code": "T-N-Z", "name": "ZN"})
        cls.node_n = cls.env["mirabilenet.node"].create(
            {"zone_id": zone.id, "code": "T-N-N", "name": "NN", "capacidad_instalada": 2})

        cls.gerencia = cls._user("t_gerencia", "gerencia")
        cls.noc_n = cls._user("t_noc_n", "noc", cls.norte)
        cls.noc_s = cls._user("t_noc_s", "noc", cls.sur)
        cls.tecnico_n = cls._user("t_tecnico_n", "tecnico", cls.norte)
        cls.vendedor_n = cls._user("t_vendedor_n", "vendedor", cls.norte)
        cls.pasante = cls._user("t_pasante", "pasante", cls.norte)

        Partner = cls.env["res.partner"]
        cls.cliente_n = Partner.create({"name": "Cliente Norte", "mirabilenet_is_customer": True,
                                        "mirabilenet_region_id": cls.norte.id})
        cls.cliente_s = Partner.create({"name": "Cliente Sur", "mirabilenet_is_customer": True,
                                        "mirabilenet_region_id": cls.sur.id})
        Plan = cls.env["product.template"]
        cls.plan_n = Plan.create(cls._plan_vals("T-NORTE", cls.norte, 200))
        cls.plan_s = Plan.create(cls._plan_vals("T-SUR", cls.sur, 300))
        cls.router_n = cls.env["mirabilenet.router"].create(
            {"name": "T-RTR-N", "region_id": cls.norte.id})
        cls.router_s = cls.env["mirabilenet.router"].create(
            {"name": "T-RTR-S", "region_id": cls.sur.id})

    @classmethod
    def _user(cls, login, role, region=None):
        user = new_test_user(cls.env, login, groups="base.group_user")
        user.write({"mirabilenet_role": role,
                    "mirabilenet_region_id": region.id if region else False})
        return user

    @classmethod
    def _plan_vals(cls, code, region, price):
        return {"name": code, "type": "service", "mirabilenet_is_plan": True,
                "mirabilenet_plan_code": code, "list_price": price,
                "mirabilenet_region_id": region.id if region else False,
                "mirabilenet_down_mbps": 20, "mirabilenet_up_mbps": 10,
                "mirabilenet_reduced_profile": "%s-REDUCIDO" % code}

    def _service(self, with_router=True, **extra):
        vals = {"partner_id": self.cliente_n.id, "plan_id": self.plan_n.id}
        if with_router:
            vals["router_id"] = self.router_n.id
        vals.update(extra)
        service = self.env["mirabilenet.service"].create(vals)
        if with_router:
            username = "usr%s" % service.id
            self.env["mirabilenet.pppoe.account"].create(
                {"service_id": service.id, "username": username, "password": "clave"})
            FakeRouterGateway.add_secret(self.router_n.wg_ip, username)
        return service

    def _connect(self, router):
        """Deja el router como lo deja un enrolamiento y un diagnóstico en verde."""
        router.sudo().write({"api_password_enc": vault.encrypt("api-pass"),
                             "wg_public_key": "PUB-%s" % router.id, "state": "conectado"})

    def _run_queue(self):
        self.env["mirabilenet.service.transition"]._cron_process()


@tagged("mirabilenet", "post_install", "-at_install")
class TestSubnets(NetworkCommon):

    def test_allocation_is_sequential_and_unique(self):
        Subnet = self.env["mirabilenet.subnet"].with_user(self.noc_n)
        first = Subnet.create({"region_id": self.norte.id})
        batch = Subnet.create([{"region_id": self.norte.id}, {"region_id": self.norte.id}])
        self.assertEqual(first.cidr, "10.65.1.0/24")
        self.assertEqual(first.gateway, "10.65.1.1")
        self.assertEqual(batch.mapped("cidr"), ["10.65.2.0/24", "10.65.3.0/24"])
        other = self.env["mirabilenet.subnet"].create({"region_id": self.sur.id})
        self.assertEqual(other.cidr, "10.66.1.0/24")
        # El tipo tiene su propia numeración, pero la red sigue siendo única.
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                Subnet.create({"region_id": self.norte.id, "kind": "lan_cliente"})

    def test_requested_network_is_ignored(self):
        subnet = self.env["mirabilenet.subnet"].with_user(self.noc_n).create(
            {"region_id": self.norte.id, "cidr": "10.99.9.0/24", "site_id": 200,
             "state": "activa"})
        self.assertEqual((subnet.cidr, subnet.site_id, subnet.state),
                         ("10.65.1.0/24", 1, "reservada"))
        with self.assertRaises(UserError):
            subnet.write({"cidr": "10.65.9.0/24"})

    def test_release_goes_to_quarantine(self):
        Subnet = self.env["mirabilenet.subnet"].with_user(self.noc_n)
        first = Subnet.create({"region_id": self.norte.id})
        first.action_release()
        self.assertEqual(first.state, "cuarentena")
        # En cuarentena su sitio no se reutiliza.
        self.assertEqual(Subnet.create({"region_id": self.norte.id}).site_id, 2)
        self.assertEqual(self.env["mirabilenet.subnet"]._cron_purge_quarantine(), 0)
        first.sudo().released_at = fields.Datetime.now() - timedelta(days=31)
        self.assertEqual(self.env["mirabilenet.subnet"]._cron_purge_quarantine(), 1)
        self.assertEqual(Subnet.create({"region_id": self.norte.id}).site_id, 1)

    def test_netmap_rules(self):
        subnet = self.env["mirabilenet.subnet"].create(
            {"region_id": self.norte.id, "legacy_network": "192.168.1.0/24"})
        self.assertIn("to-addresses=192.168.1.0/24", subnet.netmap_rules)
        self.assertIn("dst-address=10.65.1.0/24", subnet.netmap_rules)
        with self.assertRaises(ValidationError):
            subnet.legacy_network = "no-es-una-red"

    def test_subnets_are_isolated_and_role_limited(self):
        subnet = self.env["mirabilenet.subnet"].create({"region_id": self.sur.id})
        Subnet = self.env["mirabilenet.subnet"].with_user(self.noc_n)
        self.assertNotIn(subnet, Subnet.search([]))
        with self.assertRaises(AccessError):
            Subnet.create({"region_id": self.sur.id})
        with self.assertRaises(AccessError):
            self.env["mirabilenet.subnet"].with_user(self.tecnico_n).create(
                {"region_id": self.norte.id})
        with self.assertRaises(UserError):
            subnet.with_user(self.noc_s).unlink()


@tagged("mirabilenet", "post_install", "-at_install")
class TestRouters(NetworkCommon):

    def test_management_ip_is_assigned(self):
        self.assertEqual(self.router_n.wg_ip, "10.250.10.2")
        self.assertEqual(self.router_s.wg_ip, "10.250.20.2")
        second = self.env["mirabilenet.router"].with_user(self.noc_n).create(
            {"name": "T-RTR-N2", "region_id": self.norte.id, "wg_ip": "10.250.10.77",
             "state": "conectado"})
        self.assertEqual(second.wg_ip, "10.250.10.3", "la IP no la elige el operador")
        self.assertEqual(second.state, "pendiente")

    def test_system_fields_are_not_editable(self):
        router = self.router_n.with_user(self.noc_n)
        for vals in ({"state": "conectado"}, {"chk_api": True}, {"wg_public_key": "x"},
                     {"wg_ip": "10.250.10.9"}):
            with self.assertRaises(UserError):
                router.write(vals)
        router.write({"lan_networks": "192.168.50.0/24"})
        self.assertEqual(router._allowed_ips_hub(), ["10.250.10.2/32", "192.168.50.0/24"])
        with self.assertRaises(ValidationError):
            router.write({"lan_networks": "cualquier cosa"})

    def test_routers_are_isolated_and_role_limited(self):
        Router = self.env["mirabilenet.router"].with_user(self.noc_n)
        self.assertNotIn(self.router_s, Router.search([]))
        with self.assertRaises(AccessError):
            Router.browse(self.router_s.id).read(["name"])
        with self.assertRaises(AccessError):
            Router.create({"name": "T-AJENO", "region_id": self.sur.id})
        with self.assertRaises(AccessError):
            self.env["mirabilenet.router"].with_user(self.tecnico_n).create(
                {"name": "T-X", "region_id": self.norte.id})
        with self.assertRaises(AccessError):
            self.env["mirabilenet.router"].with_user(self.pasante).search([])

    def test_handshake_alone_is_not_connected(self):
        router = self.router_n.sudo()
        router.write({"identity": "MK-NORTE", "routeros_version": "7.15",
                      "wg_public_key": "PUBKEY", "api_password_enc": vault.encrypt("p")})
        self.assertEqual(router._evaluate_state(), "desconectado")
        status = {"peers": {"PUBKEY": {"latest_handshake": int(time.time()), "rx": 10,
                                       "tx": 20}}}
        Path(self.wg_dir, "status.json").write_text(json.dumps(status))
        FakeRouterGateway.unreachable.add(router.wg_ip)
        router._probe()
        self.assertTrue(router.chk_handshake)
        self.assertFalse(router.chk_ping)
        self.assertEqual(router.state, "degradado")

        FakeRouterGateway.unreachable.clear()
        FakeRouterGateway.identities[router.wg_ip] = {"identity": "OTRO", "version": "7.15"}
        router._probe()
        self.assertTrue(router.chk_api)
        self.assertFalse(router.chk_identity)
        self.assertEqual(router.state, "degradado", "la identidad no coincide")

        FakeRouterGateway.identities[router.wg_ip] = {"identity": "MK-NORTE",
                                                      "version": "7.15"}
        router._probe()
        self.assertEqual(router.state, "conectado")
        self.assertEqual(router.wg_rx_bytes, 10)
        Path(self.wg_dir, "status.json").unlink()
        router._probe()
        self.assertEqual(router.state, "desconectado")


@tagged("mirabilenet", "post_install", "-at_install")
class TestEnrollment(NetworkCommon):

    def _generate(self, router=None, user=None):
        router = (router or self.router_n).with_user(user or self.noc_n)
        return router._generate_enrollment_script()

    def _payload(self, token, **extra):
        payload = {"token": token.sudo().token, "public_key": "PUB-DEL-ROUTER=",
                   "identity": "MK-NORTE", "board": "RB750", "serial": "ABC123",
                   "version": "7.15.2", "api_address_before": "192.168.88.0/24",
                   "backup_name": "mnone-pre-enroll-x"}
        payload.update(extra)
        return payload

    def test_script_content(self):
        self.router_n.lan_networks = "192.168.50.0/24"
        script, token = self._generate()
        self.assertFalse(re.findall(r"__[A-Z_]+__", script), "quedó un marcador sin reemplazar")
        api_password = vault.decrypt(token.sudo().api_password_enc)
        for expected in (
            ':local wgAddress   "10.250.10.2/32"',
            ':local wgServerKey "LLAVE-PUBLICA-DEL-HUB="',
            ':local wgEndpoint  "vpn.example"',
            ":local wgPort      51820",
            ':local mgmtNet     "10.250.0.0/16"',
            ':local workerIp    "10.250.0.20"',
            ':local apiPassword "%s"' % api_password,
            ':local enrollToken "%s"' % token.sudo().token,
            ':local enrollUrl   "https://203.0.113.10/api/v1/network/router-enrollment/complete"',
            ':local lanNets     {"192.168.50.0/24"}',
            'common-name="CA de prueba"',
            "-----BEGIN CERTIFICATE-----\\nAAAA\\nBBBB\\n-----END CERTIFICATE-----",
            "check-certificate=yes-without-crl",
            "mtu=1412",
            "dst-port=8728",
        ):
            self.assertIn(expected, script)
        # Las llaves que envuelven el guion son parte de su seguridad.
        body = [line for line in script.splitlines() if line and not line.startswith("#")]
        self.assertEqual((body[0], body[-1]), ("{", "}"))
        self.assertNotIn("0.0.0.0/0", script.replace("(nunca 0.0.0.0/0)", ""))
        self.assertEqual(script.count("{"), script.count("}"))

    def test_template_is_the_reviewed_one(self):
        # Si esta prueba falla, la plantilla cambió: hay que revisarla en laboratorio.
        template = enrollment.ENROLLMENT_TEMPLATE
        self.assertEqual(len(template), 11419)
        self.assertEqual(template.count("BLOQUE"), 12)
        self.assertEqual(len(enrollment.OFFBOARD_TEMPLATE), 1292)

    def test_generation_needs_settings_and_role(self):
        with self.assertRaises(UserError):
            self._generate(user=self.tecnico_n)
        with self.assertRaises(AccessError):
            self._generate(router=self.router_s)
        self.env["ir.config_parameter"].set_param("mirabilenet.platform_ca_pem_path", "")
        with self.assertRaises(UserError):
            self._generate()

    def test_only_one_valid_token_at_a_time(self):
        _s, first = self._generate()
        _s, second = self._generate()
        self.assertEqual(first.state, "revocado")
        self.assertEqual(second.state, "vigente")
        status, _body = self.env["mirabilenet.enrollment.token"]._complete(
            self._payload(first), ip="198.51.100.7")
        self.assertEqual(status, 403)

    def test_token_is_single_use(self):
        _script, token = self._generate()
        Token = self.env["mirabilenet.enrollment.token"]
        status, body = Token._complete(self._payload(token), ip="198.51.100.7")
        self.assertEqual(status, 200)
        self.assertEqual(body["wg_ip"], "10.250.10.2")
        router = self.router_n
        self.assertEqual(router.state, "desconectado", "no pasa a Conectado sin diagnóstico")
        self.assertEqual((router.wg_public_key, router.identity, router.serial,
                          router.routeros_version),
                         ("PUB-DEL-ROUTER=", "MK-NORTE", "ABC123", "7.15.2"))
        self.assertTrue(router.has_credentials)
        self.assertEqual(vault.decrypt(router.sudo().api_password_enc),
                         vault.decrypt(token.sudo().api_password_enc))
        self.assertEqual(token.state, "usado")
        self.assertEqual(token.used_from_ip, "198.51.100.7")
        self.assertEqual(router.config_change_ids.kind, "enrolamiento")
        peer = json.loads(Path(self.wg_dir, "peers", "router-%s.json" % router.id).read_text())
        self.assertEqual(peer["allowed_ips"], ["10.250.10.2/32"])
        self.assertFalse(peer["revocado"])

        status, _body = Token._complete(self._payload(token, public_key="OTRA"), ip="x")
        self.assertEqual(status, 403)
        self.assertEqual(router.wg_public_key, "PUB-DEL-ROUTER=")

    def test_expired_unknown_and_incomplete(self):
        Token = self.env["mirabilenet.enrollment.token"]
        _script, token = self._generate()
        token.sudo().expires_at = fields.Datetime.now() - timedelta(minutes=1)
        self.assertEqual(Token._complete(self._payload(token), ip="x")[0], 403)
        self.assertEqual(token.state, "vencido")
        self.assertFalse(self.router_n.wg_public_key)
        self.assertEqual(Token._complete({"token": "no-existe", "public_key": "k"})[0], 403)
        self.assertEqual(Token._complete({"token": "solo-token"})[0], 400)
        self.assertEqual(Token._complete("no es un objeto")[0], 400)

    def test_expiry_cron(self):
        _script, token = self._generate()
        token.sudo().expires_at = fields.Datetime.now() - timedelta(minutes=1)
        self.env["mirabilenet.enrollment.token"]._cron_expire()
        self.assertEqual(token.state, "vencido")

    def test_token_and_secrets_are_hidden(self):
        _script, token = self._generate()
        with self.assertRaises(AccessError):
            token.with_user(self.noc_n).read(["token"])
        with self.assertRaises(AccessError):
            self.router_n.with_user(self.noc_n).read(["api_password_enc"])

    def test_offboard(self):
        _script, token = self._generate()
        self.env["mirabilenet.enrollment.token"]._complete(self._payload(token), ip="x")
        script = self.router_n.with_user(self.noc_n)._offboard()
        self.assertEqual(self.router_n.state, "retirado")
        self.assertIn('/user remove [find where name="mirabilenet_api"]', script)
        self.assertIn("address=192.168.88.0/24", script)
        peer = json.loads(
            Path(self.wg_dir, "peers", "router-%s.json" % self.router_n.id).read_text())
        self.assertTrue(peer["revocado"])
        with self.assertRaises(UserError):
            self._generate()
        self.router_n.sudo()._probe()
        self.assertEqual(self.router_n.state, "retirado")


@tagged("mirabilenet", "post_install", "-at_install")
class TestServices(NetworkCommon):

    def setUp(self):
        super().setUp()
        FakeRouterGateway.reset()

    def test_defaults_come_from_customer_and_plan(self):
        service = self._service(with_router=False)
        self.assertEqual(service.region_id, self.norte)
        self.assertEqual(service.monthly_price, 200)
        self.assertEqual(service.state, "pendiente_instalacion")
        self.assertEqual(service.payment_mode, "pospago")
        self.assertEqual(service.name, "%s - T-NORTE" % self.cliente_n.mirabilenet_code)
        discounted = self._service(with_router=False, monthly_price=150)
        self.assertEqual(discounted.monthly_price, 150)

    def test_consistency_rules(self):
        Service = self.env["mirabilenet.service"]
        with self.assertRaises(ValidationError):
            Service.create({"partner_id": self.cliente_n.id, "plan_id": self.plan_s.id})
        with self.assertRaises(ValidationError):
            Service.create({"partner_id": self.cliente_n.id, "plan_id": self.plan_n.id,
                            "router_id": self.router_s.id})
        with self.assertRaises(ValidationError):
            Service.create({"partner_id": self.cliente_n.id, "plan_id": self.plan_n.id,
                            "region_id": self.sur.id})
        proveedor = self.env["res.partner"].create({"name": "No es cliente"})
        with self.assertRaises(ValidationError):
            Service.create({"partner_id": proveedor.id, "plan_id": self.plan_n.id,
                            "region_id": self.norte.id})

    def test_state_is_not_editable(self):
        service = self._service()
        with self.assertRaises(UserError):
            service.with_user(self.tecnico_n).write({"state": "activo"})
        created = self.env["mirabilenet.service"].with_user(self.tecnico_n).create(
            {"partner_id": self.cliente_n.id, "plan_id": self.plan_n.id, "state": "activo"})
        self.assertEqual(created.state, "pendiente_instalacion")
        with self.assertRaises(UserError):
            service.with_user(self.tecnico_n).unlink()

    def test_activation_waits_for_the_router(self):
        self._connect(self.router_n)
        service = self._service()
        service.with_user(self.tecnico_n).action_activate()
        self.assertEqual(service.state, "pendiente_instalacion",
                         "no cambia hasta que el equipo confirma")
        self.assertTrue(service.pending_transition)
        self._run_queue()
        self.assertEqual(service.state, "activo")
        self.assertEqual(service.date_start, fields.Date.context_today(service))
        account = service.pppoe_ids
        self.assertTrue(account.enabled)
        self.assertEqual(account.profile, "T-NORTE")
        self.assertTrue(account.synced)
        transition = service.transition_ids
        self.assertEqual((transition.state, transition.user_id), ("confirmada", self.tecnico_n))
        log = self.env["mirabilenet.audit.log"].search(
            [("model", "=", "mirabilenet.service"), ("res_id", "=", service.id)], limit=1)
        self.assertEqual((log.action, log.user_id), ("servicio_activar", self.tecnico_n))

    def test_full_cycle(self):
        self._connect(self.router_n)
        service = self._service().with_user(self.tecnico_n)
        host, username = self.router_n.wg_ip, service.pppoe_ids.username
        service.action_activate()
        self._run_queue()
        service.action_partial_cut()
        self._run_queue()
        self.assertEqual(service.state, "moroso")
        self.assertEqual(FakeRouterGateway.secrets[host][username]["profile"],
                         "T-NORTE-REDUCIDO")
        service.action_suspend()
        self._run_queue()
        self.assertEqual(service.state, "suspendido")
        self.assertFalse(FakeRouterGateway.secrets[host][username]["enabled"])
        service.action_activate()
        self._run_queue()
        self.assertEqual(service.state, "activo")
        self.assertEqual(FakeRouterGateway.secrets[host][username],
                         {"enabled": True, "profile": "T-NORTE"})
        service.action_disconnect()
        self._run_queue()
        self.assertEqual(service.state, "activo")
        service.action_terminate()
        self.assertEqual(service.state, "activo")
        self._run_queue()
        self.assertEqual(service.state, "baja")
        self.assertTrue(service.date_end)
        self.assertFalse(FakeRouterGateway.secrets[host][username]["enabled"])
        with self.assertRaises(UserError):
            service.action_activate()

    def test_failures_retry_then_go_to_manual_review(self):
        service = self._service()  # el router sigue pendiente de enrolamiento
        service.with_user(self.tecnico_n).action_suspend()
        transition = service.transition_ids
        for expected in ("reintento", "reintento", "revision_manual"):
            self._run_queue()
            self.assertEqual(transition.state, expected)
        self.assertEqual(transition.attempts, 3)
        self.assertIn("Pendiente de enrolamiento", transition.error_detail)
        self.assertEqual(service.state, "pendiente_instalacion", "sin confirmación no cambia")
        self._run_queue()
        self.assertEqual(transition.attempts, 3, "en revisión manual ya no se reintenta sola")

        self._connect(self.router_n)
        transition.with_user(self.tecnico_n).action_retry()
        self._run_queue()
        self.assertEqual(transition.state, "confirmada")
        self.assertEqual(service.state, "suspendido")

    def test_router_error_does_not_move_the_state(self):
        self._connect(self.router_n)
        service = self._service()
        FakeRouterGateway.failures.append("Conexión cerrada por el router.")
        service.with_user(self.tecnico_n).action_activate()
        self._run_queue()
        self.assertEqual(service.state, "pendiente_instalacion")
        self.assertEqual(service.transition_ids.state, "reintento")
        self._run_queue()
        self.assertEqual(service.state, "activo")

    def test_missing_secret_or_account(self):
        self._connect(self.router_n)
        service = self._service()
        FakeRouterGateway.secrets.clear()
        service.with_user(self.tecnico_n).action_activate()
        self._run_queue()
        self.assertIn("no existe", service.transition_ids.error_detail)
        bare = self._service(with_router=False)
        bare.with_user(self.tecnico_n).action_activate()
        self._run_queue()
        self.assertIn("no tiene cuenta PPPoE", bare.transition_ids.error_detail)
        self.assertEqual(bare.state, "pendiente_instalacion")

    def test_requests_are_idempotent(self):
        service = self._service()
        first, created = service._request_transition("suspender", key="corte-1-20261120")
        again, created_again = service._request_transition("suspender", key="corte-1-20261120")
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first, again)
        self.assertEqual(len(service.transition_ids), 1)

    def test_terminate_without_equipment_is_immediate(self):
        service = self._service(with_router=False)
        service.with_user(self.tecnico_n).action_terminate()
        self.assertEqual(service.state, "baja")
        self.assertFalse(service.transition_ids)

    def test_change_plan(self):
        self._connect(self.router_n)
        service = self._service()
        other = self.env["product.template"].create(self._plan_vals("T-NORTE-50", self.norte, 400))
        service.with_user(self.tecnico_n).action_change_plan(other)
        self._run_queue()
        self.assertEqual(service.pppoe_ids.profile, "T-NORTE-50")
        self.assertEqual(service.monthly_price, 200, "el precio no cambia solo")
        self.assertEqual(service.state, "pendiente_instalacion")

    def test_who_can_give_orders(self):
        service = self._service()
        for user in (self.vendedor_n, self.pasante):
            with self.assertRaises(AccessError, msg=user.login):
                service.with_user(user).action_suspend()
        with self.assertRaises(AccessError):
            service.with_user(self.noc_s).action_suspend()
        with self.assertRaises(AccessError):
            self.env["mirabilenet.service"].with_user(self.vendedor_n).create(
                {"partner_id": self.cliente_n.id, "plan_id": self.plan_n.id})
        with self.assertRaises(UserError):
            service.transition_ids.with_user(self.tecnico_n).write({"state": "confirmada"})

    def test_services_are_isolated(self):
        service_n = self._service(with_router=False)
        service_s = self.env["mirabilenet.service"].create(
            {"partner_id": self.cliente_s.id, "plan_id": self.plan_s.id})
        account_s = self.env["mirabilenet.pppoe.account"].create(
            {"service_id": service_s.id, "username": "usr-sur", "password": "x"})
        Service = self.env["mirabilenet.service"].with_user(self.tecnico_n)
        self.assertIn(service_n, Service.search([]))
        self.assertNotIn(service_s, Service.search([]))
        with self.assertRaises(AccessError):
            Service.browse(service_s.id).read(["name"])
        with self.assertRaises(AccessError):
            account_s.with_user(self.tecnico_n).read(["username"])
        with self.assertRaises(AccessError):
            self.env["mirabilenet.service"].with_user(self.pasante).search([])
        self.assertIn(service_s,
                      self.env["mirabilenet.service"].with_user(self.gerencia).search([]))

    def test_pppoe_password_is_stored_encrypted(self):
        service = self._service()
        account = service.pppoe_ids
        self.assertFalse(account.password)
        self.assertTrue(account.has_password)
        self.assertEqual(vault.decrypt(account.sudo().password_enc), "clave")
        with self.assertRaises(AccessError):
            account.with_user(self.tecnico_n).read(["password_enc"])
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.env["mirabilenet.pppoe.account"].create(
                    {"service_id": service.id, "username": "otro"})

    def test_plan_in_use_cannot_be_deleted(self):
        service = self._service(with_router=False)
        service.with_user(self.tecnico_n).action_terminate()
        with self.assertRaises(UserError):
            self.plan_n.with_user(self.gerencia).unlink()

    def test_node_capacity(self):
        self._connect(self.router_n)
        service = self._service(node_id=self.node_n.id)
        self.assertEqual(self.node_n.capacidad_comprometida, 0)
        service.action_activate()
        self._run_queue()
        self.node_n.invalidate_recordset()
        self.assertEqual(self.node_n.capacidad_comprometida, 1)
        self.assertEqual(self.node_n.capacidad_disponible, 1)
