import base64
from datetime import date

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.misc import file_open

from ..cartera import limpieza

PLANTILLA = "mirabilenet_cartera/static/plantillas/plantilla_cartera_clientes.csv"


@tagged("mirabilenet", "post_install", "-at_install")
class TestLimpieza(TransactionCase):

    def test_headers_are_recognized_in_any_spelling(self):
        data = "Nombre;Precio;Usuario PPPoE;Perfil;C.I.;Teléfono;No. MAC;Columna rara\n" \
               "ANA;100;a1@x;20MBPS;123456 SC;71234567;aa:bb:cc:dd:ee:ff;x\n"
        columnas, filas, desconocidas = limpieza.leer_csv(data.encode("cp1252"))
        self.assertTrue({"nombre", "precio", "usuario_pppoe", "perfil", "ci", "telefono",
                         "mac"} <= columnas)
        self.assertEqual(desconocidas, ["columna_rara"])
        self.assertEqual((filas[0]["usuario_pppoe"], filas[0]["fila"]), ("a1@x", 2))

    def test_values_are_cleaned_without_inventing(self):
        self.assertEqual(limpieza.documento("7654321-1k")[:3], ("7654321", "1K", ""))
        self.assertEqual(limpieza.documento("6543210 CBBA.")[:3], ("6543210", "", "CB"))
        self.assertTrue(limpieza.documento("ACTUALIZAR")[4])
        self.assertEqual(limpieza.mac("OC41E920CC6C(13)")[0], "0C41E920CC6C")
        self.assertEqual(limpieza.mac("E0E8EG9245FD")[0], "")
        self.assertEqual(limpieza.equipo("V-SOL_TV", "V-2802GW")[:2], ("V-SOL", "V2802GW"))
        self.assertEqual(limpieza.equipo("LANLY", "HGW-E228AA")[1], "")
        self.assertEqual(limpieza.velocidad("35 MBPS-2026 CATV"), (35, True))
        self.assertEqual(limpieza.nombre("SONIA PANTOJA + CATV"), ("SONIA PANTOJA", "CATV"))
        self.assertEqual(limpieza.precio("Bs 140,50"), 140.5)


@tagged("mirabilenet", "post_install", "-at_install")
class TestImportarCartera(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref("base.user_root"))
        Region = cls.env["mirabilenet.region"]
        company = cls.env.company
        common = {"company_id": company.id, "currency_id": company.currency_id.id}
        cls.region = Region.create(dict(common, code="CART", name="Cartera", wg_region_id=40))
        cls.otra = Region.create(dict(common, code="OTRA", name="Otra", wg_region_id=41))
        cls.gerencia = cls._user("cart_gerencia", "gerencia")
        cls.admin_otra = cls._user("cart_admin_otra", "admin_regional", cls.otra)
        cls.admin_propia = cls._user("cart_admin_propia", "admin_regional", cls.region)
        cls.vendedor = cls._user("cart_vendedor", "vendedor", cls.region)
        Nap = cls.env["mirabilenet.fiber.nap"]
        cls.nap_a = Nap.create({"code": "EJ-A-01", "name": "1A", "region_id": cls.region.id,
                                "port_count": 8})
        cls.nap_b = Nap.create({"code": "EJ-B-01", "name": "1B", "region_id": cls.region.id,
                                "port_count": 8})
        with file_open(PLANTILLA, "rb") as f:
            cls.plantilla = f.read()

    @classmethod
    def _user(cls, login, role, region=None):
        user = new_test_user(cls.env, login, groups="base.group_user")
        user.write({"mirabilenet_role": role,
                    "mirabilenet_region_id": region.id if region else False})
        return user

    def _wizard(self, user=None, data=None, region=None):
        return self.env["mirabilenet.portfolio.import"].with_user(user or self.gerencia).create({
            "region_id": (region or self.region).id, "filename": "plantilla.csv",
            "file": base64.b64encode(data or self.plantilla)})

    def _services(self):
        return self.env["mirabilenet.service"].search([("region_id", "=", self.region.id)])

    # ------------------------------------------------------------------
    def test_preview_shows_the_summary_and_saves_nothing(self):
        wizard = self._wizard()
        wizard.action_preview()
        self.assertEqual(wizard.state, "preview")
        self.assertIn("Servicios a crear: 5", wizard.summary)
        self.assertIn("Clientes: 4 nuevos", wizard.summary)
        self.assertIn("Planes nuevos: 5", wizard.summary)
        self.assertIn("35 MBPS-2026 CATV", wizard.summary)
        self.assertFalse(self._services())
        review = base64.b64decode(wizard.review_file).decode("utf-8-sig")
        self.assertIn("ANA SUAREZ;sin C.I.", review)

    def test_import_creates_plans_customers_services_pppoe_and_onu(self):
        wizard = self._wizard()
        wizard.action_preview()
        wizard.action_import()
        self.assertEqual(wizard.state, "done")
        services = self._services()
        self.assertEqual(len(services), 5)
        self.assertEqual(set(services.mapped("state")), {"activo"})
        self.assertFalse(services.mapped("transition_ids"), "no se mandan órdenes a routers")
        # Planes que no existían: uno por perfil, con la velocidad y el precio de la planilla.
        Plan = self.env["product.template"]
        catv = Plan.search([("mirabilenet_plan_code", "=", "CART-35-MBPS-2026-CATV")])
        self.assertEqual((catv.mirabilenet_down_mbps, catv.mirabilenet_includes_tv,
                          catv.list_price, catv.mirabilenet_ppp_profile,
                          catv.mirabilenet_region_id),
                         (35, True, 170, "35 MBPS-2026 CATV", self.region))
        self.assertEqual(Plan.search_count([("mirabilenet_region_id", "=", self.region.id),
                                            ("mirabilenet_is_plan", "=", True)]), 5)
        # El mismo cliente con dos servicios es un solo cliente.
        juan = services.mapped("partner_id").filtered(lambda p: p.name == "JUAN PEREZ ROJAS")
        self.assertEqual(len(juan), 1)
        self.assertEqual(len(services.filtered(lambda s: s.partner_id == juan)), 2)
        self.assertEqual((juan.vat, juan.mirabilenet_state, juan.street2),
                         ("1234567", "activo", "B/ VILLA BELEN"))
        self.assertAlmostEqual(juan.partner_latitude, -17.404, places=3)
        # La nota escrita en el nombre se mueve a las notas.
        carlos = services.mapped("partner_id").filtered(lambda p: p.name == "CARLOS GUTIERREZ")
        self.assertIn("CATV", carlos.comment)
        # Pospago: cobra el día del alta.
        maria = services.filtered(lambda s: s.partner_id.name == "MARIA LOPEZ VACA")
        self.assertEqual((maria.payment_mode, maria.date_start, maria.billing_day),
                         ("pospago", date(2026, 11, 3), 3))
        account = maria.pppoe_ids
        self.assertEqual((account.username, account.fixed_ip, account.profile),
                         ("ejemplo002@siete", "192.168.200.11", "14MBPS-2023100"))
        # ONU: una serie por servicio que la trae, instalada en el cliente.
        lots = self.env["stock.lot"].search([("mirabilenet_region_id", "=", self.region.id)])
        self.assertEqual(len(lots), 4)
        lot = lots.filtered(lambda l: l.name == "DC90E6000002")
        self.assertEqual((lot.mirabilenet_state, lot.mirabilenet_partner_id, lot.mirabilenet_mac,
                          lot.product_id.mirabilenet_brand),
                         ("en_cliente", maria.partner_id, "E0E8E6000002", "C-DATA"))
        # Lo que falta queda anotado para el técnico.
        ana = services.filtered(lambda s: s.partner_id.name == "ANA SUAREZ")
        self.assertIn("sin C.I.", ana.notes)
        self.assertIn("ONU sin número de serie", ana.partner_id.comment)
        self.assertTrue(self.env["mirabilenet.audit.log"].search(
            [("action", "=", "importar_cartera"), ("region_id", "=", self.region.id)]))

    def test_importing_twice_does_not_duplicate(self):
        self._wizard().action_import()
        second = self._wizard()
        second.action_preview()
        self.assertIn("Servicios a crear: 0 (ya importados: 5)", second.summary)
        self.assertIn("Clientes: 0 nuevos, 4 ya existen", second.summary)
        second.action_import()
        self.assertEqual(len(self._services()), 5)
        self.assertEqual(self.env["res.partner"].search_count(
            [("mirabilenet_region_id", "=", self.region.id),
             ("mirabilenet_is_customer", "=", True)]), 4)

    def test_a_pppoe_from_another_region_is_rejected(self):
        self._wizard(region=self.otra, data=(
            "NOMBRE;PRECIO DEL PAQUETE;USUARIO PPPoE;PLAN win box\n"
            "OTRO CLIENTE;140;ejemplo001@siete;35MBPS-2026140\n").encode()).action_import()
        wizard = self._wizard()
        wizard.action_import()
        self.assertEqual(len(self._services()), 4)
        review = base64.b64decode(wizard.review_file).decode("utf-8-sig")
        self.assertIn("NO SE IMPORTÓ: el usuario PPPoE ejemplo001@siete ya existe en otra región",
                      review)

    def test_rows_without_required_data_are_not_imported(self):
        data = ("NOMBRE;PRECIO DEL PAQUETE;USUARIO PPPoE;PLAN win box\n"
                "SIN PRECIO;;u1@x;20MBPS\n"
                "BIEN;100;u2@x;20MBPS\n").encode()
        wizard = self._wizard(data=data)
        wizard.action_import()
        self.assertEqual(self._services().mapped("pppoe_ids.username"), ["u2@x"])
        self.assertIn("NO SE IMPORTA: precio ilegible",
                      base64.b64decode(wizard.review_file).decode("utf-8-sig"))
        with self.assertRaisesRegex(UserError, "faltan columnas obligatorias"):
            self._wizard(data=b"NOMBRE;PRECIO\nA;1\n").action_preview()

    def test_only_plan_managers_of_the_region_can_import(self):
        with self.assertRaises(AccessError):
            self._wizard(user=self.vendedor).action_preview()
        with self.assertRaises(AccessError):
            self._wizard(user=self.admin_otra).action_preview()
        wizard = self._wizard(user=self.admin_propia)
        wizard.action_preview()
        self.assertEqual(wizard.state, "preview")

    # ------------------------------------------------------------------
    # Caja NAP y puerto
    # ------------------------------------------------------------------
    def _port(self, nap, number):
        return nap.port_ids.filtered(lambda p: p.number == number)

    def test_each_service_gets_its_box_and_port(self):
        wizard = self._wizard()
        wizard.action_preview()
        self.assertIn("Servicios con caja NAP y puerto: 4", wizard.summary)
        wizard.action_import()
        services = self._services()
        juan_1 = services.filtered(lambda s: s.pppoe_ids.username == "ejemplo001@siete")
        juan_2 = services.filtered(lambda s: s.pppoe_ids.username == "ejemplo004@siete")
        self.assertEqual(self._port(self.nap_a, 1).service_id, juan_1)
        self.assertEqual(self._port(self.nap_a, 3).service_id, juan_2, "«1A» es el nombre")
        self.assertEqual(self._port(self.nap_b, 1).service_ip, "192.168.200.12")
        self.assertEqual(juan_1.fiber_nap_id, self.nap_a)
        ana = services.filtered(lambda s: s.pppoe_ids.username == "ejemplo005@siete")
        self.assertFalse(ana.fiber_port_id, "sin caja en la planilla no se asigna")
        self.assertEqual(self.nap_a.ports_used, 3)

    def test_uploading_again_with_boxes_assigns_already_imported_services(self):
        sin_cajas = "\n".join(";".join(line.split(";")[:18])
                              for line in self.plantilla.decode("utf-8-sig").splitlines())
        self._wizard(data=sin_cajas.encode()).action_import()
        self.assertFalse(self._services().mapped("fiber_port_id"))
        wizard = self._wizard()
        wizard.action_import()
        self.assertEqual(len(self._services()), 5, "no se duplican los servicios")
        self.assertEqual(len(self._services().mapped("fiber_port_id")), 4)
        self.assertIn("Puertos NAP asignados: 4", wizard.summary)
        # Una tercera vez no cambia nada.
        again = self._wizard()
        again.action_import()
        self.assertIn("Puertos NAP que ya estaban asignados: 4", again.summary)

    def test_box_problems_are_reported_not_guessed(self):
        head = "NOMBRE;PRECIO DEL PAQUETE;USUARIO PPPoE;PLAN win box;CAJA NAP;PUERTO\n"
        rows = ("UNO;100;p1@x;20MBPS;EJ-A-01;5\n"
                "DOS;100;p2@x;20MBPS;EJ-A-01;5\n"
                "TRES;100;p3@x;20MBPS;NO-EXISTE;1\n"
                "CUATRO;100;p4@x;20MBPS;EJ-A-01;9\n"
                "CINCO;100;p5@x;20MBPS;EJ-B-01;\n"
                "SEIS;100;p6@x;20MBPS;EJ-B-01;2\n")
        self._port(self.nap_b, 2).state = "danado"
        wizard = self._wizard(data=(head + rows).encode())
        # En la revisión, el puerto repetido dentro de la misma planilla.
        wizard.action_preview()
        self.assertIn("el puerto 5 de EJ-A-01 también figura para p1@x",
                      base64.b64decode(wizard.review_file).decode("utf-8-sig"))
        self.assertIn("Servicios con caja NAP y puerto: 1", wizard.summary)
        wizard.action_import()
        self.assertEqual(len(self._services()), 6, "el problema de la caja no frena el servicio")
        self.assertEqual(self._port(self.nap_a, 5).service_id.partner_id.name, "UNO")
        review = base64.b64decode(wizard.review_file).decode("utf-8-sig")
        for text in ("el puerto 5 de EJ-A-01 ya es de UNO",
                     "la caja NO-EXISTE no existe en la región",
                     "la caja EJ-A-01 tiene 8 puertos: no existe el puerto 9",
                     "falta el PUERTO de la caja EJ-B-01",
                     "el puerto 2 de EJ-B-01 está marcado como dañado"):
            self.assertIn(text, review)
        self.assertEqual(self.nap_a.ports_used + self.nap_b.ports_used, 1)
        # Un puerto ya ocupado por otro cliente en Odoo tampoco se pisa.
        other = self._wizard(data=(head + "SIETE;100;p7@x;20MBPS;EJ-A-01;5\n").encode())
        other.action_import()
        self.assertIn("el puerto 5 de EJ-A-01 ya es de UNO",
                      base64.b64decode(other.review_file).decode("utf-8-sig"))

    # ------------------------------------------------------------------
    # Una planilla otro día: completar sin choques
    # ------------------------------------------------------------------
    HEAD = ("NOMBRE;PRECIO DEL PAQUETE;USUARIO PPPoE;PLAN win box;MODALIDAD DE PAGO;IP REMOTA;"
            "C.I.;TELEFONO;BARRIO;DIRECCION;MARCA;MODELO;No. De SERIE;No. MAC;FECHA SOLICITUD;"
            "FECHA ACTIVACION;LATITUD;LONGITUD\n")
    DIA1 = ("ROSA QUISPE;140;dia_a@x;35MBPS;prepago;;;;;;;;;;;;;\n"
            "LUIS MAMANI;100;dia_b@x;14MBPS;prepago;10.0.0.2;5555555 SC;71111111;B/ CENTRO;"
            "Calle 2;V-SOL;V2802GW;VDIA00000002;4CD7C8DDDD02;01/11/2026;02/11/2026;-17,40;"
            "-63,88\n")
    DIA2 = ("ROSA QUISPE;140;dia_a@x;35MBPS;prepago;10.0.0.1;4444444 SC;72222222;B/ NORTE;"
            "Calle 1;C-DATA;FD511GW-X-R310;DCDIA0000001;E0E8DDDD0001;01/11/2026;03/11/2026;"
            "-17,41;-63,87\n"
            "LUIS MAMANI;120;dia_b@x;20MBPS;prepago;10.0.0.2;5555555 SC;73333333;B/ CENTRO;"
            "Calle 2;V-SOL;V2802GW;VDIA00000002;4CD7C8DDDD02;01/11/2026;02/11/2026;-17,40;"
            "-63,88\n"
            "PEDRO NUEVO;90;dia_c@x;10MBPS;prepago;10.0.0.1;;74444444;;;;;;;;;;\n")

    def _account(self, username):
        return self.env["mirabilenet.pppoe.account"].search([("username", "=", username)])

    def _review(self, wizard):
        return base64.b64decode(wizard.review_file).decode("utf-8-sig")

    def test_second_upload_completes_the_first_without_duplicating(self):
        self._wizard(data=(self.HEAD + self.DIA1).encode()).action_import()
        wizard = self._wizard(data=(self.HEAD + self.DIA2).encode())
        wizard.action_preview()
        self.assertIn("Clientes: 1 nuevos, 2 ya existen", wizard.summary)
        wizard.action_import()
        Partner = self.env["res.partner"]
        rosa = Partner.search([("name", "=", "ROSA QUISPE"),
                               ("mirabilenet_region_id", "=", self.region.id)])
        self.assertEqual(len(rosa), 1, "la segunda planilla no duplica al cliente")
        self.assertEqual((rosa.vat, rosa.phone, rosa.street2), ("4444444", "72222222", "B/ NORTE"))
        self.assertAlmostEqual(rosa.partner_latitude, -17.41)
        cuenta = self._account("dia_a@x")
        self.assertEqual((cuenta.fixed_ip, cuenta.service_id.date_start.isoformat()),
                         ("10.0.0.1", "2026-11-03"))
        self.assertEqual(self.env["stock.lot"].search(
            [("name", "=", "DCDIA0000001")]).mirabilenet_partner_id, rosa)
        # Lo que ya estaba cargado y vino distinto no se cambia: se lista.
        luis = self._account("dia_b@x")
        self.assertEqual((luis.service_id.monthly_price, luis.service_id.partner_id.phone),
                         (100, "71111111"))
        review = self._review(wizard)
        self.assertIn("precio mensual distinto: en Odoo 100, en la planilla 120", review)
        self.assertIn("teléfono distinto: en Odoo 71111111, en la planilla 73333333", review)
        self.assertIn("plan distinto", review)
        # La IP repetida dentro de la planilla no se le da a dos clientes.
        self.assertFalse(self._account("dia_c@x").fixed_ip)
        self.assertIn("IP 10.0.0.1 repetida en la planilla", review)
        self.assertIn("Datos completados", wizard.summary)
        self.assertIn("Datos distintos sin cambiar: 3", wizard.summary)

    def test_replace_option_applies_the_new_values(self):
        self._wizard(data=(self.HEAD + self.DIA1).encode()).action_import()
        wizard = self._wizard(data=(self.HEAD + self.DIA2).encode())
        wizard.replace_data = True
        wizard.action_import()
        luis = self._account("dia_b@x").service_id
        self.assertEqual((luis.monthly_price, luis.partner_id.phone), (120, "73333333"))
        self.assertEqual(luis.plan_id.mirabilenet_ppp_profile, "14MBPS",
                         "el plan nunca se cambia solo: afecta a la red y al cobro")
        self.assertIn("Datos reemplazados: 2", wizard.summary)

    def test_repeated_pppoe_user_in_the_file_is_not_imported_twice(self):
        data = (self.HEAD + "UNO;100;rep@x;20MBPS;;;;;;;;;;;;;;\n"
                            "OTRO;100;rep@x;20MBPS;;;;;;;;;;;;;;\n").encode()
        wizard = self._wizard(data=data)
        wizard.action_import()
        self.assertEqual(self._account("rep@x").service_id.partner_id.name, "UNO")
        self.assertFalse(self.env["res.partner"].search([("name", "=", "OTRO")]))
        self.assertIn("usuario PPPoE rep@x repetido en la planilla (fila 2)",
                      self._review(wizard))

    def test_an_ip_already_used_in_odoo_is_not_given_to_another_customer(self):
        self._wizard(data=(self.HEAD + self.DIA1).encode()).action_import()
        data = (self.HEAD + "NUEVA;100;nueva@x;20MBPS;;10.0.0.2;;;;;;;;;;;;\n").encode()
        wizard = self._wizard(data=data)
        wizard.action_import()
        self.assertTrue(self._account("nueva@x"), "el servicio se importa igual")
        self.assertFalse(self._account("nueva@x").fixed_ip)
        self.assertIn("la IP 10.0.0.2 ya es de LUIS MAMANI", self._review(wizard))

    def test_two_services_in_different_places_are_not_a_difference(self):
        data = (self.HEAD +
                "ANA DOS;100;casa@x;20MBPS;;;7777777;71234567;B/ NORTE;Casa;;;;;;;-17,40;-63,88\n"
                "ANA DOS;100;tienda@x;20MBPS;;;7777777;71234567;B/ SUR;Tienda;;;;;;;-17,41;-63,87\n"
                ).encode()
        self._wizard(data=data).action_import()
        again = self._wizard(data=data)
        again.action_preview()
        self.assertIn("0 distintos", again.summary)
        tienda = self._account("tienda@x").service_id
        self.assertEqual(tienda.install_address, "Tienda, B/ SUR")
