from datetime import date, timedelta

from odoo import fields
from odoo.tests import new_test_user, tagged
from odoo.tests.common import BaseCase

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from ..tablero import periodos


@tagged("mirabilenet", "post_install", "-at_install")
class TestPeriodos(BaseCase):

    def test_ranges_include_today(self):
        today = date(2026, 11, 22)
        self.assertEqual(periodos.rango("hoy", today), (today, today))
        self.assertEqual(periodos.rango("7", today), (date(2026, 11, 16), today))
        self.assertEqual(periodos.rango("90", today)[0], today - timedelta(days=89))
        self.assertEqual(periodos.rango("otro", today), periodos.rango("30", today))

    def test_six_months_end_with_the_current_one(self):
        months = periodos.meses_atras(date(2026, 2, 10), 6)
        self.assertEqual([m[2] for m in months],
                         ["sep 25", "oct 25", "nov 25", "dic 25", "ene 26", "feb 26"])
        self.assertEqual(months[-1][:2], (date(2026, 2, 1), date(2026, 2, 28)))

    def test_no_total_means_no_percentage(self):
        self.assertIsNone(periodos.porcentaje(3, 0))
        self.assertEqual(periodos.porcentaje(1, 3), 33.3)
        self.assertIsNone(periodos.disponible(0, 5))
        self.assertEqual(periodos.disponible(10, 12), 0)


@tagged("mirabilenet", "post_install", "-at_install")
class TestDashboard(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref("base.user_root"))
        cls.today = fields.Date.context_today(cls.env.user)
        company = cls.env.company
        Region = cls.env["mirabilenet.region"]
        common = {"company_id": company.id, "currency_id": company.currency_id.id}
        cls.norte = Region.create(dict(common, code="D-N", name="Norte tablero", wg_region_id=61))
        cls.sur = Region.create(dict(common, code="D-S", name="Sur tablero", wg_region_id=62))
        zone = cls.env["mirabilenet.zone"].create(
            {"region_id": cls.norte.id, "code": "D-N-Z", "name": "Zona tablero"})
        cls.env["mirabilenet.node"].create(
            {"zone_id": zone.id, "code": "D-N-N", "name": "Nodo tablero",
             "capacidad_instalada": 10})
        cls.plan = cls.env["product.template"].create({
            "name": "Plan tablero", "type": "service", "mirabilenet_is_plan": True,
            "mirabilenet_plan_code": "D-PLAN", "list_price": 100,
            "mirabilenet_down_mbps": 20, "mirabilenet_up_mbps": 10})
        Partner = cls.env["res.partner"]
        cls.customers = {}
        for name, region, state in (("Ana Prueba", cls.norte, "activo"),
                                    ("Beto Prueba", cls.norte, "moroso"),
                                    ("Caro Prueba", cls.norte, "prospecto"),
                                    ("Dani Prueba", cls.sur, "activo")):
            cls.customers[name] = Partner.create({
                "name": name, "mirabilenet_is_customer": True,
                "mirabilenet_region_id": region.id, "mirabilenet_state": state})
        cls.s_activo = cls._service("Ana Prueba", "activo")
        cls.s_moroso = cls._service("Beto Prueba", "moroso")
        cls.s_pendiente = cls._service("Caro Prueba", "pendiente_instalacion")
        cls.s_sur = cls._service("Dani Prueba", "activo")
        # Una vencida hace 10 días, otra que vence en 3 y otra del sur vencida.
        cls.overdue = cls._invoice(cls.s_moroso, 300, cls.today - timedelta(days=10))
        cls.soon = cls._invoice(cls.s_activo, 100, cls.today + timedelta(days=3))
        cls.overdue_sur = cls._invoice(cls.s_sur, 500, cls.today - timedelta(days=5))
        cls.paid = cls._invoice(cls.s_activo, 100, cls.today)
        cls.paid._mirabilenet_register_payment()
        Router = cls.env["mirabilenet.router"]
        cls.router = Router.create({"name": "D-RTR-N", "region_id": cls.norte.id})
        cls.router.state = "conectado"
        Router.create({"name": "D-RTR-N2", "region_id": cls.norte.id}).state = "degradado"
        Pppoe = cls.env["mirabilenet.pppoe.account"]
        Pppoe.create({"service_id": cls.s_activo.id, "username": "d-ana@prueba",
                      "synced": True})
        Pppoe.create({"service_id": cls.s_moroso.id, "username": "d-beto@prueba",
                      "synced": False})
        cls.finanzas_n = cls._user("d_finanzas_n", "finanzas", cls.norte)
        cls.gerencia = cls._user("d_gerencia", "gerencia")
        # Odoo muestra una avería a quien la pidió, la atiende o la sigue: la atiende gerencia.
        cls.env["maintenance.request"].create({"name": "Avería tablero",
                                               "user_id": cls.gerencia.id,
                                               "mirabilenet_service_id": cls.s_activo.id})
        cls.Dashboard = cls.env["mirabilenet.dashboard"]

    @classmethod
    def _user(cls, login, role, region=None):
        user = new_test_user(cls.env, login, groups="base.group_user")
        user.write({"mirabilenet_role": role,
                    "mirabilenet_region_id": region.id if region else False})
        return user

    @classmethod
    def _service(cls, partner_name, state):
        service = cls.env["mirabilenet.service"].create(
            {"partner_id": cls.customers[partner_name].id, "plan_id": cls.plan.id,
             "date_start": cls.today})
        service.state = state
        return service

    @classmethod
    def _invoice(cls, service, price, due):
        move = cls.env["account.move"].create({
            "move_type": "out_invoice", "partner_id": service.partner_id.id,
            "invoice_date": min(due, cls.today), "invoice_date_due": due,
            "mirabilenet_service_id": service.id,
            "mirabilenet_region_id": service.region_id.id,
            "invoice_line_ids": [(0, 0, {"product_id": cls.plan.product_variant_id.id,
                                         "quantity": 1, "price_unit": price,
                                         "tax_ids": [(5, 0, 0)]})]})
        move.action_post()
        move.invoice_date_due = due
        return move

    def _data(self, user=None, period="30", region=False):
        dashboard = self.Dashboard.with_user(user) if user else self.Dashboard
        return dashboard.get_dashboard_data(period, region.id if region else False)

    def test_numbers_of_one_region(self):
        data = self._data(self.gerencia, region=self.norte)
        self.assertEqual(data["resumen"]["clientes_activos"], 1)
        self.assertEqual(data["resumen"]["servicios_total"], 3)
        self.assertEqual(data["resumen"]["cartera_vencida"], 300)
        self.assertEqual(data["resumen"]["ingresos"], 100)
        self.assertEqual(data["cobros"]["vence_7"], 100)
        self.assertEqual(data["cobros"]["hoy"], 100)
        self.assertEqual(data["cobros"]["recibos_hoy"], 1)
        states = {s["clave"]: s["cantidad"] for s in data["servicios_estado"]}
        self.assertEqual(states, {"pendiente_instalacion": 1, "activo": 1, "moroso": 1,
                                  "suspendido": 0, "baja": 0})
        self.assertEqual(data["clientes"]["clientes_total"], 3)
        self.assertEqual(data["clientes"]["clientes_prospectos"], 1)
        self.assertEqual(data["clientes"]["clientes_morosos"], 1)
        self.assertEqual(data["red"]["routers_total"], 2)
        self.assertEqual(data["red"]["routers_conectados"], 1)
        self.assertEqual(data["red"]["pppoe_total"], 2)
        self.assertEqual(data["red"]["pppoe_desincronizadas"], 1)
        self.assertEqual(data["capacidad"]["instalada"], 10)
        self.assertEqual(data["capacidad"]["ocupada"], 2)
        self.assertEqual(data["capacidad"]["disponible"], 8)
        self.assertEqual(data["capacidad"]["ocupacion"], 20.0)
        self.assertEqual(data["soporte"]["averias_abiertas"], 1)
        self.assertEqual(data["soporte"]["instalaciones_pendientes"], 1)
        self.assertEqual([c["cliente"] for c in data["cartera"]["clientes"]], ["Beto Prueba"])
        self.assertEqual(data["cartera"]["clientes"][0]["dias"], 10)
        self.assertEqual(data["ultimos_pagos"][0]["monto"], 100)
        self.assertEqual(sum(d["monto"] for d in data["cobranza_diaria"]["dias"]), 100)
        self.assertEqual(sum(m["monto"] for m in data["cobranza_metodo"]), 100)
        self.assertEqual(data["ingresos_gastos"]["meses"][-1]["ingresos"], 100)

    def test_what_is_not_measured_is_blank_not_zero(self):
        data = self._data(self.gerencia, region=self.sur)
        self.assertIsNone(data["red"]["sesiones_en_linea"])
        self.assertIsNone(data["red"]["trafico"])
        # El sur no declara capacidad: no hay ocupación que calcular.
        self.assertIsNone(data["capacidad"]["instalada"])
        self.assertIsNone(data["capacidad"]["ocupacion"])
        self.assertIsNone(data["capacidad"]["disponible"])
        # Sin facturas de proveedor no se inventan gastos.
        flow = data["ingresos_gastos"]
        self.assertFalse(flow["con_gastos"])
        self.assertIsNone(flow["margen"])
        self.assertTrue(all(m["gastos"] is None for m in flow["meses"]))

    def test_regional_user_sees_only_its_region(self):
        north = self._data(self.finanzas_n)
        self.assertEqual(north["resumen"]["cartera_vencida"], 300)
        self.assertEqual(north["titulo_region"], "Norte tablero")
        self.assertFalse(north["es_global"])
        self.assertEqual(north["regiones"], [])
        # Aunque pida otra región, no la ve: decide la regla, no el navegador.
        forced = self._data(self.finanzas_n, region=self.sur)
        self.assertEqual(forced["resumen"]["cartera_vencida"], 300)
        everyone = self._data(self.gerencia)
        self.assertEqual(everyone["resumen"]["cartera_vencida"], 800)
        self.assertTrue(everyone["es_global"])
        self.assertIn(self.sur.id, [r["id"] for r in everyone["regiones"]])

    def test_each_card_opens_the_records_it_counts(self):
        data = self._data(self.gerencia, region=self.norte)
        expected = {
            "servicios_activos": data["resumen"]["clientes_activos"],
            "servicios_total": data["resumen"]["servicios_total"],
            "clientes_total": data["clientes"]["clientes_total"],
            "clientes_morosos": data["clientes"]["clientes_morosos"],
            "routers_conectados": data["red"]["routers_conectados"],
            "pppoe_desincronizadas": data["red"]["pppoe_desincronizadas"],
            "averias_abiertas": data["soporte"]["averias_abiertas"],
            "pagos_hoy": data["cobros"]["recibos_hoy"],
            "servicios_moroso": 1,
            "cartera_vencida": 1,
        }
        Dashboard = self.Dashboard.with_user(self.gerencia)
        for key, count in expected.items():
            action = Dashboard.action_open(key, "30", self.norte.id)
            found = self.env[action["res_model"]].with_user(self.gerencia).search_count(
                action["domain"])
            self.assertEqual(found, count, key)

    def test_setup_steps(self):
        setup = self._data(self.gerencia, region=self.norte)["puesta_en_marcha"]
        steps = {s["clave"]: s["hecho"] for s in setup["pasos"]}
        self.assertEqual(setup["total"], 8)
        self.assertTrue(steps["capacidad"])
        self.assertTrue(steps["router"])
        self.assertTrue(steps["servicio"])
        self.assertFalse(steps["region"])  # sin sucursal todavía
        self.assertTrue(setup["router_listo"])
        for step in setup["pasos"]:
            self.assertTrue(self.env.ref(step["accion"], raise_if_not_found=False), step["accion"])

    def test_it_is_the_home_screen(self):
        action = self.env.ref("mirabilenet_dashboard.action_mirabilenet_dashboard")
        self.assertEqual(action.tag, "mirabilenet_dashboard.tablero")
        menu = self.env.ref("mirabilenet_dashboard.menu_mirabilenet_dashboard")
        self.assertEqual(menu.parent_id, self.env.ref("mirabilenet_base.menu_mirabilenet_root"))
        self.assertEqual(self.env["ir.default"]._get("res.users", "action_id"), action.id)
        new = new_test_user(self.env, "d_nuevo", groups="base.group_user")
        self.assertEqual(new.action_id.id, action.id)
