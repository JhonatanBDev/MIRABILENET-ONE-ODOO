from datetime import date, timedelta

from odoo import fields
from odoo.tests import new_test_user, tagged
from odoo.tests.common import BaseCase

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from ..tablero import negocio, periodos


@tagged("mirabilenet", "post_install", "-at_install")
class TestTablero(BaseCase):
    """Cuentas puras: periodos e indicadores de negocio."""

    def test_ranges_include_today(self):
        today = date(2026, 11, 22)
        self.assertEqual(periodos.rango("hoy", today), (today, today))
        self.assertEqual(periodos.rango("7", today), (date(2026, 11, 16), today))
        self.assertEqual(periodos.rango("90", today)[0], today - timedelta(days=89))
        self.assertEqual(periodos.rango("otro", today), periodos.rango("30", today))
        self.assertEqual(periodos.rango("mes", today), (date(2026, 11, 1), today))
        self.assertEqual(periodos.rango("mes_anterior", today),
                         (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(periodos.rango("rango", today, date(2026, 9, 30), date(2026, 9, 1)),
                         (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual(periodos.rango("rango", today), periodos.rango("30", today))

    def test_previous_period_has_the_same_length(self):
        self.assertEqual(periodos.anterior(date(2026, 11, 1), date(2026, 11, 30)),
                         (date(2026, 10, 2), date(2026, 10, 31)))

    def test_six_months_end_with_the_current_one(self):
        months = periodos.meses_atras(date(2026, 2, 10), 6)
        self.assertEqual([m[2] for m in months],
                         ["sep 25", "oct 25", "nov 25", "dic 25", "ene 26", "feb 26"])
        self.assertEqual(months[-1][:2], (date(2026, 2, 1), date(2026, 2, 28)))

    def test_no_base_means_no_number(self):
        self.assertIsNone(periodos.porcentaje(3, 0))
        self.assertEqual(periodos.porcentaje(1, 3), 33.3)
        self.assertIsNone(periodos.disponible(0, 5))
        self.assertEqual(periodos.disponible(10, 12), 0)
        self.assertIsNone(negocio.arpu(500, 0))
        self.assertEqual(negocio.arpu(500, 4), 125)
        self.assertIsNone(negocio.churn(2, 0))
        self.assertEqual(negocio.churn(1, 50), 2.0)
        self.assertIsNone(negocio.recaudacion(100, 0))
        self.assertEqual(negocio.recaudacion(75, 100), 75.0)
        self.assertIsNone(negocio.variacion(10, 0))
        self.assertEqual(negocio.variacion(150, 100), 50.0)
        self.assertEqual(negocio.variacion(50, 100), -50.0)

    def test_aging_buckets(self):
        today = date(2026, 11, 22)
        rows = negocio.antiguedad([
            (today - timedelta(days=5), 100, 1),
            (today - timedelta(days=30), 50, 2),
            (today - timedelta(days=31), 70, 1),
            (today - timedelta(days=120), 30, 3),
            (today + timedelta(days=3), 999, 4),  # todavía no vence: no cuenta
        ], today)
        by_key = {r["clave"]: r for r in rows}
        self.assertEqual([r["clave"] for r in rows], ["0_30", "31_60", "61_90", "90_mas"])
        self.assertEqual((by_key["0_30"]["monto"], by_key["0_30"]["clientes"]), (150, 2))
        self.assertEqual(by_key["31_60"]["monto"], 70)
        self.assertEqual(by_key["61_90"]["facturas"], 0)
        self.assertEqual(by_key["90_mas"]["monto"], 30)


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
        cls.norte = Region.create(dict(common, code="D-N", name="Norte tablero", wg_region_id=61,
                                       objetivo_mrr=1000, precio_referencia=100))
        cls.sur = Region.create(dict(common, code="D-S", name="Sur tablero", wg_region_id=62))
        cls.zone = cls.env["mirabilenet.zone"].create(
            {"region_id": cls.norte.id, "code": "D-N-Z", "name": "Zona tablero"})
        cls.node = cls.env["mirabilenet.node"].create(
            {"zone_id": cls.zone.id, "code": "D-N-N", "name": "Nodo tablero",
             "capacidad_instalada": 10})
        Plan = cls.env["product.template"]
        plan_values = {"type": "service", "mirabilenet_is_plan": True,
                       "mirabilenet_down_mbps": 20, "mirabilenet_up_mbps": 10}
        cls.plan = Plan.create(dict(plan_values, name="Plan tablero", list_price=100,
                                    mirabilenet_plan_code="D-PLAN"))
        cls.plan_fibra = Plan.create(dict(plan_values, name="Plan fibra tablero", list_price=200,
                                          mirabilenet_plan_code="D-FIBRA"))
        Partner = cls.env["res.partner"]
        cls.customers = {}
        for name, region, state in (("Ana Prueba", cls.norte, "activo"),
                                    ("Beto Prueba", cls.norte, "moroso"),
                                    ("Caro Prueba", cls.norte, "prospecto"),
                                    ("Dani Prueba", cls.sur, "activo"),
                                    ("Eva Prueba", cls.norte, "cancelado")):
            cls.customers[name] = Partner.create({
                "name": name, "mirabilenet_is_customer": True,
                "mirabilenet_region_id": region.id, "mirabilenet_state": state})
        cls.s_activo = cls._service("Ana Prueba", "activo", node=cls.node)
        cls.s_moroso = cls._service("Beto Prueba", "moroso", plan=cls.plan_fibra)
        cls.s_pendiente = cls._service("Caro Prueba", "pendiente_instalacion")
        cls.s_sur = cls._service("Dani Prueba", "activo")
        # Un servicio de hace dos meses que se dio de baja este mes: cuenta para el churn.
        cls.s_baja = cls._service("Eva Prueba", "baja",
                                  start=cls.today - timedelta(days=70), end=cls.today)
        # Una vencida hace 10 días, otra hace 45, una que vence en 3 y otra del sur vencida.
        cls.overdue = cls._invoice(cls.s_moroso, 300, cls.today - timedelta(days=10))
        cls.overdue_old = cls._invoice(cls.s_moroso, 50, cls.today - timedelta(days=45))
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
        Pppoe.create({"service_id": cls.s_sur.id, "username": "d-dani@prueba",
                      "synced": False})
        cls.finanzas_n = cls._user("d_finanzas_n", "finanzas", cls.norte)
        cls.gerencia = cls._user("d_gerencia", "gerencia")
        cls.noc_n = cls._user("d_noc_n", "noc", cls.norte)
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
    def _service(cls, partner_name, state, plan=None, node=None, start=None, end=None):
        service = cls.env["mirabilenet.service"].create(
            {"partner_id": cls.customers[partner_name].id, "plan_id": (plan or cls.plan).id,
             "node_id": node.id if node else False, "date_start": start or cls.today})
        service.write({"state": state, "date_end": end})
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

    @staticmethod
    def _ids(filters):
        return {k: (v.id if hasattr(v, "_name") else v) for k, v in filters.items()}

    def _data(self, user=None, **filters):
        dashboard = self.Dashboard.with_user(user) if user else self.Dashboard
        return dashboard.get_dashboard_data(self._ids(filters))

    def _count_opened(self, user, key, **filters):
        """Lo que abre la tarjeta: debe contar lo mismo que muestra."""
        action = self.Dashboard.with_user(user).action_open(key, self._ids(filters))
        return self.env[action["res_model"]].with_user(user).search_count(action["domain"])

    def test_numbers_of_one_region(self):
        data = self._data(self.gerencia, region_id=self.norte)
        self.assertEqual(data["resumen"]["clientes_activos"], 1)
        self.assertEqual(data["resumen"]["servicios_total"], 4)
        self.assertEqual(data["resumen"]["cartera_vencida"], 350)
        self.assertEqual(data["resumen"]["ingresos"], 100)
        self.assertEqual(data["cobros"]["vence_7"], 100)
        self.assertEqual(data["cobros"]["hoy"], 100)
        states = {s["clave"]: s["cantidad"] for s in data["servicios_estado"]}
        self.assertEqual(states, {"pendiente_instalacion": 1, "activo": 1, "moroso": 1,
                                  "suspendido": 0, "baja": 1})
        self.assertEqual(data["clientes"]["clientes_total"], 4)
        self.assertEqual(data["clientes"]["clientes_prospectos"], 1)
        self.assertEqual(data["clientes"]["clientes_bajas"], 1)
        # Altas por la fecha de alta del servicio, no por cuándo se cargó el cliente.
        self.assertEqual(data["clientes"]["altas_hoy"], 3)
        self.assertEqual(data["red"]["routers_total"], 2)
        self.assertEqual(data["red"]["routers_conectados"], 1)
        self.assertEqual(data["red"]["pppoe_total"], 2)
        self.assertEqual(data["red"]["pppoe_desincronizadas"], 1)
        self.assertEqual(data["capacidad"]["instalada"], 10)
        self.assertEqual(data["capacidad"]["ocupada"], 2)
        self.assertEqual(data["capacidad"]["ocupacion"], 20.0)
        self.assertEqual(data["soporte"]["averias_abiertas"], 1)
        self.assertEqual(data["soporte"]["instalaciones_pendientes"], 1)
        self.assertEqual([c["cliente"] for c in data["cartera"]["clientes"]], ["Beto Prueba"])
        self.assertEqual(data["cartera"]["clientes"][0]["dias"], 45)
        self.assertEqual(data["ultimos_pagos"][0]["monto"], 100)
        self.assertEqual(sum(d["monto"] for d in data["cobranza_diaria"]["dias"]), 100)
        self.assertEqual(sum(m["monto"] for m in data["cobranza_metodo"]), 100)
        self.assertEqual(data["ingresos_gastos"]["meses"][-1]["ingresos"], 100)

    def test_business_indicators(self):
        n = self._data(self.gerencia, region_id=self.norte)["negocio"]
        # MRR: activo (100) + moroso (200 del plan de fibra).
        self.assertEqual(n["mrr"], 300)
        self.assertEqual(n["arpu"], 150)
        self.assertEqual(n["objetivo"], 1000)
        self.assertEqual(n["avance"], 30.0)
        # Este mes: 1 baja sobre 1 servicio que había al empezar el mes.
        self.assertEqual(n["bajas_mes"], 1)
        self.assertEqual(n["churn"], 100.0)
        self.assertEqual(n["movimientos"][-1]["altas"], 3)
        # La de hace 45 días se emitió fuera de los 30 días del periodo.
        self.assertEqual(n["facturado"], 500)
        self.assertEqual(n["recaudacion"], 20.0)
        aging = {t["clave"]: t["monto"] for t in n["antiguedad"]}
        self.assertEqual(aging, {"0_30": 300, "31_60": 50, "61_90": 0, "90_mas": 0})
        self.assertEqual(n["top_mora"], [{"nombre": "Sin zona asignada", "monto": 350}])

    def test_filters_narrow_every_number(self):
        by_plan = self._data(self.gerencia, region_id=self.norte, plan_id=self.plan_fibra)
        self.assertEqual(by_plan["resumen"]["servicios_total"], 1)
        self.assertEqual(by_plan["resumen"]["cartera_vencida"], 350)
        self.assertEqual(by_plan["red"]["pppoe_total"], 1)
        self.assertEqual(by_plan["negocio"]["mrr"], 200)
        # Con un filtro de plan el objetivo de la región ya no se compara.
        self.assertIsNone(by_plan["negocio"]["objetivo"])
        by_node = self._data(self.gerencia, node_id=self.node)
        self.assertEqual(by_node["resumen"]["servicios_total"], 1)
        self.assertEqual(by_node["resumen"]["cartera_vencida"], 0)
        self.assertEqual(by_node["capacidad"]["instalada"], 10)
        by_state = self._data(self.gerencia, region_id=self.norte, service_state="moroso")
        self.assertEqual(by_state["resumen"]["servicios_total"], 1)
        self.assertEqual(by_state["clientes"]["clientes_total"], 1)
        # La distribución por estado no se recorta: así se puede elegir otro.
        self.assertEqual(len([s for s in by_state["servicios_estado"] if s["cantidad"]]), 4)
        self.assertEqual([c["clave"] for c in by_state["filtros"]["chips"]],
                         ["region_id", "service_state"])
        # Lo que no es un filtro conocido no hace nada.
        junk = self._data(self.gerencia, region_id=self.norte, period="x", plan_id="abc",
                          service_state="inventado", payment_mode="otro")
        self.assertEqual(junk["resumen"]["servicios_total"], 4)
        self.assertEqual(junk["filtros"]["period"], "30")

    def test_period_and_comparison(self):
        last_month = self._data(self.gerencia, region_id=self.norte, period="mes_anterior")
        self.assertEqual(last_month["resumen"]["ingresos"], 0)
        self.assertEqual(last_month["resumen"]["altas"], 0)
        this_month = self._data(self.gerencia, region_id=self.norte, period="mes")
        self.assertEqual(this_month["resumen"]["altas"], 3)
        # Sin cobros en el periodo anterior no hay variación que calcular.
        self.assertIsNone(this_month["resumen"]["ingresos_variacion"])
        rango = self._data(self.gerencia, region_id=self.norte, period="rango",
                           date_from=fields.Date.to_string(self.today - timedelta(days=80)),
                           date_to=fields.Date.to_string(self.today - timedelta(days=60)))
        self.assertEqual(rango["resumen"]["altas"], 1)
        self.assertEqual(rango["filtros"]["period"], "rango")

    def test_what_is_not_measured_is_blank_not_zero(self):
        data = self._data(self.gerencia, region_id=self.sur)
        self.assertIsNone(data["red"]["sesiones_en_linea"])
        self.assertIsNone(data["red"]["trafico"])
        # El sur no tiene router conectado: sus cuentas no pueden estar «desincronizadas».
        self.assertIsNone(data["red"]["pppoe_desincronizadas"])
        self.assertIsNone(data["capacidad"]["instalada"])
        self.assertIsNone(data["capacidad"]["ocupacion"])
        flow = data["ingresos_gastos"]
        self.assertFalse(flow["con_gastos"])
        self.assertIsNone(flow["margen"])
        self.assertTrue(all(m["gastos"] is None for m in flow["meses"]))
        self.assertIsNone(data["negocio"]["objetivo"])

    def test_alerts_only_when_something_needs_attention(self):
        north = {a["clave"]: a for a in self._data(self.gerencia, region_id=self.norte)["alertas"]}
        self.assertEqual(north["routers_alerta"]["cantidad"], 1)
        self.assertEqual(north["vencidas_30"]["cantidad"], 1)
        self.assertIn("servicios_facturan", north)  # MRR por debajo del objetivo
        self.assertNotIn("comprobantes_revision", north)
        south = self._data(self.gerencia, region_id=self.sur)["alertas"]
        self.assertEqual(south, [])

    def test_regional_user_sees_only_its_region(self):
        north = self._data(self.finanzas_n)
        self.assertEqual(north["resumen"]["cartera_vencida"], 350)
        self.assertEqual(north["titulo_region"], "Norte tablero")
        self.assertFalse(north["es_global"])
        # Aunque pida otra región, no la ve: decide la regla, no el navegador.
        forced = self._data(self.finanzas_n, region_id=self.sur)
        self.assertEqual(forced["resumen"]["cartera_vencida"], 350)
        self.assertEqual(forced["filtros"]["chips"], [])
        options = self.Dashboard.with_user(self.finanzas_n).get_filter_options()
        self.assertEqual(options["regiones"], [])
        everyone = self._data(self.gerencia)
        self.assertEqual(everyone["resumen"]["cartera_vencida"], 850)
        self.assertTrue(everyone["es_global"])
        options = self.Dashboard.with_user(self.gerencia).get_filter_options()
        self.assertIn(self.sur.id, [r["id"] for r in options["regiones"]])
        self.assertIn(self.zone.id, [z["id"] for z in options["zonas"]])
        node = [n for n in options["nodos"] if n["id"] == self.node.id][0]
        self.assertEqual((node["region_id"], node["zone_id"]), (self.norte.id, self.zone.id))

    def test_each_card_opens_the_records_it_counts(self):
        for filters in ({"region_id": self.norte}, {"region_id": self.norte, "plan_id": self.plan},
                        {"node_id": self.node}, {"service_state": "moroso"}):
            data = self._data(self.gerencia, **filters)
            expected = {
                "servicios_activos": data["resumen"]["clientes_activos"],
                "servicios_total": data["resumen"]["servicios_total"],
                "altas_periodo": data["resumen"]["altas"],
                "clientes_total": data["clientes"]["clientes_total"],
                "clientes_morosos": data["clientes"]["clientes_morosos"],
                "altas_hoy": data["clientes"]["altas_hoy"],
                "routers_conectados": data["red"]["routers_conectados"],
                "pppoe_total": data["red"]["pppoe_total"],
                "averias_abiertas": data["soporte"]["averias_abiertas"],
            }
            for key, count in expected.items():
                self.assertEqual(self._count_opened(self.gerencia, key, **filters), count,
                                 (key, filters))
        aging = self._data(self.gerencia, region_id=self.norte)["negocio"]["antiguedad"]
        for row in aging:
            self.assertEqual(self._count_opened(self.gerencia, "cartera_" + row["clave"],
                                                region_id=self.norte), row["facturas"])

    def test_preferences_and_layout_by_role(self):
        Dashboard = self.Dashboard.with_user(self.noc_n)
        saved = Dashboard.save_preferences({
            "filtros": {"period": "mes", "plan_id": self.plan.id, "otra_cosa": 1},
            "ocultas": ["negocio", "inventada"]})
        self.assertEqual(saved, {"filtros": {"period": "mes", "plan_id": self.plan.id},
                                 "ocultas": ["negocio"]})
        self.assertEqual(Dashboard.get_filter_options()["preferencias"], saved)
        layout = Dashboard.get_dashboard_data({})["secciones"]
        self.assertEqual(layout["orden"][:3], ["alertas", "operacion", "capacidad"])
        self.assertEqual(layout["ocultas"], ["negocio"])
        # Cada usuario guarda lo suyo.
        self.assertEqual(self.Dashboard.with_user(self.gerencia).get_filter_options()[
            "preferencias"], {})
        self.assertEqual(self._data(self.gerencia)["secciones"]["orden"][0], "alertas")

    def test_setup_steps(self):
        setup = self._data(self.gerencia, region_id=self.norte)["puesta_en_marcha"]
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
