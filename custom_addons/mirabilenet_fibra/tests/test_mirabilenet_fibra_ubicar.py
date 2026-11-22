from odoo.exceptions import AccessError
from odoo.tests import tagged

from .test_mirabilenet_fibra import FiberCommon


@tagged("mirabilenet", "post_install", "-at_install")
class TestStandardPorts(FiberCommon):

    def test_a_new_nap_gets_the_standard_ports(self):
        Nap = self.env["mirabilenet.fiber.nap"]
        nap = Nap.create({"code": "F-STD-01", "region_id": self.norte.id})
        self.assertEqual(nap.port_count, 8)
        self.assertEqual(nap.port_ids.mapped("number"), list(range(1, 9)))
        self.env["ir.config_parameter"].sudo().set_param(
            "mirabilenet_fibra.default_port_count", "16")
        self.assertEqual(Nap.create({"code": "F-STD-02", "region_id": self.norte.id}).port_count,
                         16)
        # 0 sigue siendo «no se sabe», si alguien lo pide a propósito.
        unknown = Nap.create({"code": "F-STD-03", "region_id": self.norte.id, "port_count": 0})
        self.assertTrue(unknown.ports_missing)

    def test_naps_without_ports_are_brought_to_the_standard(self):
        Nap = self.env["mirabilenet.fiber.nap"]
        empty = Nap.create({"code": "F-STD-04", "region_id": self.norte.id, "port_count": 0})
        twelve = Nap.create({"code": "F-STD-05", "region_id": self.norte.id, "port_count": 12})
        changed = Nap._mirabilenet_apply_standard_ports()
        self.assertEqual(changed, 1)
        self.assertEqual((empty.port_count, len(empty.port_ids)), (8, 8))
        self.assertEqual(twelve.port_count, 12, "una caja ya definida no se toca")


@tagged("mirabilenet", "post_install", "-at_install")
class TestLocateCustomer(FiberCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Pppoe = cls.env["mirabilenet.pppoe.account"]
        Pppoe.create({"service_id": cls.service.id, "username": "cliente1@siete",
                      "fixed_ip": "192.168.99.8"})
        Pppoe.create({"service_id": cls.service2.id, "username": "cliente2@siete",
                      "fixed_ip": "192.168.99.9"})
        cls.nap.address_reference = "Esquina de la plaza, poste 3"
        cls.port3 = cls.nap.port_ids.filtered(lambda p: p.number == 3)
        cls.port3.service_id = cls.service
        cls.port5 = cls.nap.port_ids.filtered(lambda p: p.number == 5)
        cls.port5.service_id = cls.service2

    def _locate(self, query, user=None):
        wizard = self.env["mirabilenet.fiber.locate"].with_user(user or self.tecnico_n).create(
            {"query": query})
        wizard.action_search()
        return wizard

    def test_each_port_shows_the_ip_of_its_customer(self):
        self.assertEqual((self.port3.service_ip, self.port3.pppoe_username),
                         ("192.168.99.8", "cliente1@siete"))
        Port = self.env["mirabilenet.fiber.port"]
        self.assertEqual(Port.search([("service_ip", "=", "192.168.99.8")]), self.port3)
        self.port3.action_release()
        self.assertFalse(self.port3.service_ip)

    def test_the_ip_leads_to_the_box_and_how_to_get_there(self):
        wizard = self._locate("192.168.99.8")
        self.assertEqual(wizard.service_id, self.service)
        self.assertEqual((wizard.nap_id, wizard.port_id), (self.nap, self.port3))
        self.assertIn("Esquina de la plaza, poste 3", wizard.result)
        self.assertIn("Puerto 3", wizard.result)
        self.assertIn("https://www.google.com/maps/dir/?api=1&amp;destination=-17.4,-63.88",
                      wizard.result)
        # Los vecinos de la caja, para ver si el problema es de la caja.
        self.assertIn("Cliente Fibra Norte 2", wizard.result)
        self.assertIn("192.168.99.9", wizard.result)
        # También por usuario PPPoE o por nombre.
        self.assertEqual(self._locate("cliente1@siete").service_id, self.service)
        self.assertEqual(self._locate("fibra norte 2").service_id, self.service2)

    def test_several_open_failures_in_the_box_point_to_the_box(self):
        Request = self.env["maintenance.request"]
        for service in (self.service, self.service2):
            Request.create({"name": "Sin internet", "mirabilenet_service_id": service.id})
        wizard = self._locate("192.168.99.8")
        self.assertIn("2 averías abiertas en esta caja", wizard.result)
        self.assertIn("revise primero la caja", wizard.result)

    def test_a_customer_without_a_box_says_so(self):
        self.port3.action_release()
        wizard = self._locate("192.168.99.8")
        self.assertEqual(wizard.service_id, self.service)
        self.assertFalse(wizard.nap_id)
        self.assertIn("no tiene caja NAP asignada", wizard.result)
        self.assertIn("No se encontró", self._locate("10.9.9.9").result)

    def test_search_respects_the_region(self):
        self.assertIn("No se encontró", self._locate("192.168.99.8", self.tecnico_s).result)
        with self.assertRaises(AccessError):
            self._locate("192.168.99.8", self.cajero_n)


@tagged("mirabilenet", "post_install", "-at_install")
class TestReimportNaps(FiberCommon):
    HEAD = ("codigo;nombre_nap;localidad;zona_barrio;ramal;latitud;longitud;"
            "direccion_referencia;puertos_totales;puertos_ocupados;puertos_danados;olt;puerto_pon;"
            "color_de_hilo_alimentador;estado\n")

    def test_a_later_file_completes_and_reports_what_it_replaces(self):
        self._import(nap_csv=(self.HEAD + "F-RE-01;R1;Yapacani;;;;;Poste 1;;;;;;;por_verificar\n"
                              ).encode())
        nap = self.env["mirabilenet.fiber.nap"].search([("code", "=", "F-RE-01")])
        nap.address_reference = "Poste 12, corregido en Odoo"
        later = (self.HEAD + "F-RE-01;R1;Yapacani;Centro;;-17.404864;-63.884567;Poste 1;;;;"
                 "OLT-9;4;;activa\n").encode()
        # Conservar: completa lo vacío y no pisa la corrección hecha en Odoo.
        kept = self._import(nap_csv=later, keep_existing=True)
        self.assertEqual(nap.address_reference, "Poste 12, corregido en Odoo")
        self.assertEqual((nap.olt, nap.neighborhood, nap.state), ("OLT-9", "Centro", "activa"))
        self.assertAlmostEqual(nap.latitude, -17.404864)
        self.assertIn("se conserva", kept.log)
        # Sin conservar: el archivo manda, pero queda escrito qué cambió.
        replaced = self._import(nap_csv=later)
        self.assertEqual(nap.address_reference, "Poste 1")
        self.assertIn("actualizado: Dirección o referencia «Poste 12, corregido en Odoo» → "
                      "«Poste 1»", replaced.log)
