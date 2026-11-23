from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("mirabilenet", "post_install", "-at_install")
class TestMirabilenetPos(TestPoSCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        su = cls.env(su=True)
        currency = cls.basic_config.currency_id
        su.ref("mirabilenet_pos.pricelist_branch").write(
            {"currency_id": currency.id, "company_id": False})
        Region = su["mirabilenet.region"]
        cls.norte = Region.create({"code": "P-N", "name": "Norte cajas", "wg_region_id": 53,
                                   "currency_id": currency.id})
        cls.sur = Region.create({"code": "P-S", "name": "Sur cajas", "wg_region_id": 54,
                                 "currency_id": currency.id})
        Branch = su["mirabilenet.branch"]
        cls.branch_n = Branch.create({"region_id": cls.norte.id, "code": "PN1", "name": "Centro"})
        cls.branch_s = Branch.create({"region_id": cls.sur.id, "code": "PS1", "name": "Sur"})
        cls.plan = su["product.template"].create({
            "name": "Hogar 20", "type": "service", "mirabilenet_is_plan": True,
            "mirabilenet_plan_code": "P-HOGAR", "list_price": 300,
            "mirabilenet_down_mbps": 20, "mirabilenet_up_mbps": 10}).product_variant_id
        cls.installation = su.ref("mirabilenet_pos.product_installation")
        cls.basic_config.sudo().mirabilenet_branch_id = cls.branch_n
        cls.cajero_n = cls._user("p_cajero_n", "cajero", cls.norte)
        cls.cajero_s = cls._user("p_cajero_s", "cajero", cls.sur)

    @classmethod
    def _user(cls, login, role, region):
        user = new_test_user(cls.env, login, groups="base.group_user")
        user.sudo().write({"mirabilenet_role": role, "mirabilenet_region_id": region.id})
        return user

    def setUp(self):
        super().setUp()
        self.config = self.basic_config

    def _sell(self, lines, customer=None, paid=None):
        total = paid if paid is not None else 0
        orders = self._create_orders([{
            "pos_order_lines_ui_args": lines, "customer": customer,
            "payments": [(self.cash_pm1, total)]}])
        return next(iter(orders.values()))

    def test_branch_point_of_sale_uses_the_branch_pricelist(self):
        pricelist = self.env.ref("mirabilenet_pos.pricelist_branch")
        self.assertEqual(self.config.pricelist_id, pricelist)
        self.assertEqual(self.config.mirabilenet_region_id, self.norte)
        self.assertEqual(self.plan.categ_id, self.env.ref("mirabilenet_pos.product_category_plans"))
        self.assertTrue(self.plan.available_in_pos)
        self.assertEqual(pricelist._get_product_price(self.plan, 1), 0)
        self.assertEqual(pricelist._get_product_price(self.product_a, 1), self.product_a.lst_price)

    def test_selling_a_plan_requests_the_service(self):
        self.open_new_session()
        customer = self.env["res.partner"].create({"name": "Vecina Nueva", "street": "Calle 1"})
        order = self._sell([(self.plan, 1), (self.installation, 1)], customer=customer)
        service = order.mirabilenet_service_ids
        self.assertEqual(len(service), 1)
        self.assertEqual((service.partner_id, service.plan_id, service.region_id, service.state),
                         (customer, self.plan.product_tmpl_id, self.norte,
                          "pendiente_instalacion"))
        self.assertEqual(service.install_address, "Calle 1")
        self.assertEqual(order.amount_total, 0, "el plan no se cobra en caja")
        self.assertTrue(customer.mirabilenet_is_customer)
        self.assertEqual((customer.mirabilenet_region_id, customer.mirabilenet_branch_id),
                         (self.norte, self.branch_n))
        self.assertEqual(customer.mirabilenet_state, "instalacion_pendiente")
        self.assertEqual(len(self.env["mirabilenet.audit.log"].sudo().search(
            [("model", "=", "mirabilenet.service"), ("res_id", "=", service.id)])), 1)
        order._mirabilenet_request_services()
        self.assertEqual(len(order.mirabilenet_service_ids), 1, "repetir no duplica")

    def test_other_sales_do_not_create_services(self):
        self.open_new_session()
        order = self._sell([(self.installation, 1)], customer=self.customer)
        self.assertFalse(order.mirabilenet_service_ids)
        with self.assertRaises(UserError):
            self._sell([(self.plan, 1)])

    def test_branches_are_isolated_by_region(self):
        self.open_new_session()
        order = self._sell([(self.plan, 1)], customer=self.customer)
        Order = self.env["pos.order"]
        self.assertEqual(Order.with_user(self.cajero_n).search([("id", "=", order.id)]), order)
        self.assertFalse(Order.with_user(self.cajero_s).search([("id", "=", order.id)]))
        with self.assertRaises(AccessError):
            order.with_user(self.cajero_s).read(["amount_total"])
        Config = self.env["pos.config"]
        self.assertFalse(Config.with_user(self.cajero_s).search([("id", "=", self.config.id)]))
        self.assertTrue(self.cajero_n.has_group("point_of_sale.group_pos_user"))

    def test_saving_settings_keeps_the_branch_pricelist(self):
        """Con «Listas de precios» apagada, guardar Ajustes no archiva la de las sucursales y
        el aviso de archivado no sale por ella."""
        Settings = self.env["res.config.settings"].sudo()
        pricelist = self.env.ref("mirabilenet_pos.pricelist_branch").sudo()
        pricelist.action_unarchive()  # la base de pruebas del punto de venta la deja archivada
        others = self.env["product.pricelist"].sudo().search([("id", "!=", pricelist.id)])
        others.action_archive()
        self.env.ref("base.group_user").sudo().write(
            {"implied_ids": [(3, self.env.ref("product.group_product_pricelist").id)]})
        settings = Settings.create({"group_product_pricelist": False})
        self.assertFalse(settings._onchange_group_sale_pricelist())
        settings.execute()
        pricelist.invalidate_recordset()
        self.assertTrue(pricelist.active)
        self.assertEqual(self.config.pricelist_id, pricelist)
        # Si hubiera otra lista activa, el aviso sí sale.
        others[:1].action_unarchive()
        if others:
            self.assertIn("warning", Settings.create(
                {"group_product_pricelist": False})._onchange_group_sale_pricelist())
