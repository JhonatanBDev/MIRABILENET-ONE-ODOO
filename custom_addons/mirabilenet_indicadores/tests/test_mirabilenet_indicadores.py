from odoo import fields
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("mirabilenet", "post_install", "-at_install")
class TestIndicadores(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref("base.user_root"))
        company = cls.env.company
        Region = cls.env["mirabilenet.region"]
        common = {"company_id": company.id, "currency_id": company.currency_id.id}
        cls.norte = Region.create(dict(common, code="I-N", name="Norte ind", wg_region_id=44))
        cls.sur = Region.create(dict(common, code="I-S", name="Sur ind", wg_region_id=45))
        Partner = cls.env["res.partner"]
        cls.cliente_n = Partner.create({"name": "Cliente Norte", "mirabilenet_is_customer": True,
                                        "mirabilenet_region_id": cls.norte.id,
                                        "phone": "71000001"})
        cls.cliente_s = Partner.create({"name": "Cliente Sur", "mirabilenet_is_customer": True,
                                        "mirabilenet_region_id": cls.sur.id})
        cls.plan = cls.env["product.template"].create({
            "name": "Hogar 20", "type": "service", "mirabilenet_is_plan": True,
            "mirabilenet_plan_code": "I-HOGAR", "list_price": 300,
            "mirabilenet_down_mbps": 20, "mirabilenet_up_mbps": 10})
        cls.service_n = cls._service(cls.cliente_n)
        cls.service_s = cls._service(cls.cliente_s)
        cls.invoice_n = cls._invoice(cls.service_n, 300)
        cls.invoice_s = cls._invoice(cls.service_s, 200)
        cls.finanzas_n = cls._user("i_finanzas_n", "finanzas", cls.norte)
        cls.gerencia = cls._user("i_gerencia", "gerencia")
        cls.instance = cls.env.ref("mirabilenet_indicadores.mis_instance_cobranza")

    @classmethod
    def _user(cls, login, role, region=None):
        user = new_test_user(cls.env, login, groups="base.group_user")
        user.write({"mirabilenet_role": role,
                    "mirabilenet_region_id": region.id if region else False})
        return user

    @classmethod
    def _service(cls, partner):
        service = cls.env["mirabilenet.service"].create(
            {"partner_id": partner.id, "plan_id": cls.plan.id,
             "date_start": fields.Date.context_today(cls.env.user)})
        service.state = "activo"
        return service

    @classmethod
    def _invoice(cls, service, price):
        move = cls.env["account.move"].create({
            "move_type": "out_invoice", "partner_id": service.partner_id.id,
            "invoice_date": fields.Date.context_today(cls.env.user),
            "mirabilenet_service_id": service.id,
            "mirabilenet_region_id": service.region_id.id,
            "invoice_line_ids": [(0, 0, {"product_id": cls.plan.product_variant_id.id,
                                         "quantity": 1, "price_unit": price,
                                         "tax_ids": [(5, 0, 0)]})]})
        move.action_post()
        return move

    def _values(self, user):
        """Valores del mes actual y del mes anterior, por indicador."""
        result = self.instance.with_user(user).compute()
        return {row["description"] or row["label"]: (row["cells"][-1].get("val"),
                                                      row["cells"][-2].get("val"))
                for row in result["body"]}

    def test_collections_respect_the_region(self):
        self.invoice_n._mirabilenet_register_payment(amount=150)
        north = self._values(self.finanzas_n)
        self.assertEqual(north["Facturado en el mes (Bs)"][0], 300)
        self.assertEqual(north["Cobrado en el mes (Bs)"][0], 150)
        self.assertAlmostEqual(north["Tasa de recaudación"][0], 0.5)
        self.assertEqual(north["Pendiente de lo facturado (Bs)"][0], 150)
        self.assertEqual(north["Servicios facturados"][0], 1)
        self.assertEqual(north["Ingreso medio por servicio, ARPU (Bs)"][0], 300)
        self.assertEqual(north["Altas de servicio"][0], 1)
        everyone = self._values(self.gerencia)
        self.assertEqual(everyone["Facturado en el mes (Bs)"][0], 500)
        self.assertEqual(everyone["Servicios facturados"][0], 2)

    def test_an_empty_month_is_blank_not_zero(self):
        previous = self._values(self.finanzas_n)
        for name in ("Facturado en el mes (Bs)", "Tasa de recaudación",
                     "Ingreso medio por servicio, ARPU (Bs)"):
            self.assertIsNone(previous[name][1], name)

    def test_only_delivered_notices_count(self):
        branch = self.env["mirabilenet.branch"].create(
            {"region_id": self.norte.id, "code": "IN1", "name": "Centro"})
        number = self.env["mirabilenet.whatsapp.number"].create(
            {"branch_id": branch.id, "phone_number_id": "I-PN", "display_number": "+59170000009"})
        template = self.env["mirabilenet.whatsapp.template"].create(
            {"event": "aviso_emitido", "meta_name": "aviso_ind", "variables": "cliente"})
        now = fields.Datetime.now()
        Message = self.env["mirabilenet.whatsapp.message"]
        for index, state in enumerate(("enviado", "entregado", "leido", "fallido", "pendiente")):
            Message.create({"partner_id": self.cliente_n.id, "region_id": self.norte.id,
                            "number_id": number.id, "template_id": template.id,
                            "event": "aviso_emitido", "destination": "59171000001",
                            "unique_key": "ind-%d" % index, "state": state, "sent_at": now})
        values = self._values(self.finanzas_n)
        self.assertEqual(values["Avisos de WhatsApp enviados (cantidad, no Bs)"][0], 3)

    def test_mrr_goal_alert(self):
        zone = self.env["mirabilenet.zone"].create(
            {"region_id": self.norte.id, "code": "IZ1", "name": "Zona"})
        self.env["mirabilenet.node"].create({"zone_id": zone.id, "region_id": self.norte.id,
                                             "code": "IND1", "name": "Nodo",
                                             "capacidad_instalada": 10})
        region = self.norte.with_user(self.finanzas_n)
        self.assertEqual(region.mirabilenet_goal_state, "sin_datos")
        self.assertTrue(region.mirabilenet_goal_message.startswith("—"))
        self.norte.write({"objetivo_mrr": 2000, "precio_referencia": 300})
        region.invalidate_recordset()
        self.assertEqual((region.mirabilenet_mrr, region.mirabilenet_capacity,
                          region.mirabilenet_ceiling, region.mirabilenet_customers_needed),
                         (300, 10, 3000, 7))
        self.assertEqual(region.mirabilenet_goal_state, "alcanzable")
        self.norte.objetivo_mrr = 5000
        region.invalidate_recordset()
        self.assertEqual(region.mirabilenet_goal_state, "no_alcanzable")
        self.assertIn("17 clientes", region.mirabilenet_goal_message)
        self.assertIn("500.00", region.mirabilenet_goal_message)
