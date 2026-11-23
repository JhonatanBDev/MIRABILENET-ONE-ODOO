from decimal import Decimal

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import BaseCase

from ..cotizador import almacenamiento, desde_texto, pedido, precios

D = Decimal


@tagged("mirabilenet", "post_install", "-at_install")
class TestMotor(BaseCase):
    """Casos de la §13 de MIGRACION_ODOO19.md (los recargos son de prueba, no los reales)."""

    def test_sale_price_markup_and_rounding(self):
        cfg = precios.Config()
        self.assertEqual(precios.precio_venta(cfg, D("629"), D("0.50")), D("945.00"))  # 943,50 sube a 945
        # Por debajo de 50 Bs se redondea a 0,50.
        self.assertEqual(precios.precio_venta(cfg, D("2.95"), D("0.30")), D("4.00"))
        self.assertEqual(precios.precio_venta(cfg, D("3.10"), D("0.30")), D("4.50"))

    def test_taxes(self):
        cfg = precios.Config()
        taxes = precios.calcular_impuestos(cfg, D("1000"), True)
        self.assertEqual((taxes.iva, taxes.it, taxes.total), (D("130.00"), D("30.00"),
                                                              D("1160.00")))
        self.assertEqual(precios.calcular_impuestos(cfg, D("1000"), False).total, D("1000.00"))
        gross = precios.calcular_impuestos(precios.Config(modo_impuestos="bruto"), D("840"), True)
        self.assertEqual(gross.total, D("1000.00"))

    def test_markup_order_and_limits(self):
        cfg = precios.Config(por_categoria={"camaras ip": "0.20"}, por_costo=[("10", "1.00")])
        self.assertEqual(precios.recargo_para(cfg, "CAMARAS IP", costo_item=D("300")), D("0.20"))
        self.assertEqual(precios.recargo_para(cfg, "CAMARAS IP", costo_item=D("5")), D("1.00"))
        self.assertEqual(precios.recargo_para(cfg, "OTRA", costo_item=D("300")), D("0.30"))
        with self.assertRaises(ValueError):
            precios.validar_recargo(cfg, D("0.80"), D("300"))
        precios.validar_recargo(cfg, D("1.20"), D("5"))  # ítem barato: tope mayor

    def test_storage(self):
        cfg = precios.Config()
        calc = almacenamiento.calcular(cfg, [almacenamiento.GrupoCamaras(4, 4)], 15)
        self.assertEqual(calc.tb_requeridos, 2.14)

    def test_free_text(self):
        hints = pedido.analizar("6 cámaras para mi tienda, 2 afuera, que graben 20 días")
        self.assertEqual((hints.total, hints.interior, hints.exterior, hints.dias), (6, 4, 2, 20))
        req = desde_texto.requisitos_desde_texto("cámaras económicas para mi casa, 4 cámaras")
        self.assertEqual((req["tecnologia"], req["gama"]), ("analogica", "economica"))
        self.assertTrue(req["dudas"])
        with self.assertRaises(desde_texto.PedidoError):
            desde_texto.requisitos_desde_texto("hola, quiero información")


@tagged("mirabilenet", "post_install", "-at_install")
class TestCotizacion(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Markup = cls.env["mirabilenet.cot.markup"]
        Markup.search([]).unlink()
        for category, pct in (("CAMARAS IP", 20), ("GRABADORES IP", 20),
                              ("DISCOS DUROS Y SERVIDORES", 20), ("CABLES DE RED", 20)):
            Markup.create({"kind": "categoria", "category": category, "markup": pct})
        now = fields.Datetime.now()
        stock = {"La Paz": 30, "El Alto": 5}
        Product = cls.env["product.template"]

        def product(sku, name, cost, category, brand="DAHUA"):
            return Product.create({
                "name": name, "type": "consu", "standard_price": cost, "sale_ok": True,
                "mirabilenet_cot_sku": sku, "mirabilenet_cot_category": category,
                "mirabilenet_cot_brand": brand, "mirabilenet_cot_cost_at": now,
                "mirabilenet_cot_stock": stock, "mirabilenet_cot_stock_total": 35,
                "mirabilenet_cot_offer_bot": True})

        cls.bullet = product("T-CAM-B", "CAMARA IP BULLET 4MP *PoE *IP67 EXTERIOR", 300,
                             "CAMARAS IP")
        cls.dome = product("T-CAM-D", "CAMARA IP DOMO 4MP *PoE *IP67", 280, "CAMARAS IP")
        cls.nvr = product("T-NVR", "GRABADOR NVR 8CH *8 PUERTOS POE *1 HDD HASTA 8TB", 600,
                          "GRABADORES IP")
        cls.disk = product("T-HDD4", "DISCO DURO PURPLE 4TB", 650, "DISCOS DUROS Y SERVIDORES",
                           "WD")
        cls.cable = product("T-UTP", "CABLE UTP CAT6 EXT 305 METROS", 900, "CABLES DE RED", "X")
        cls.partner = cls.env["res.partner"].create({"name": "Cliente de Prueba Cotizador",
                                                     "phone": "70000077"})
        cls.kit = cls.env.ref("mirabilenet_cotizador.kit_casa_4")
        cls.Engine = cls.env["mirabilenet.cot.engine"]

    def _quote(self, **kw):
        return self.Engine.create_from_kit(self.kit, "La Paz", self.partner, **kw)

    def test_quote_from_kit(self):
        order = self._quote()
        self.assertTrue(order.name.startswith("COT-"))
        self.assertEqual(order.mirabilenet_cot_stage, "borrador")
        sections = order.order_line.filtered(lambda l: l.display_type == "line_section")
        self.assertEqual(sections.mapped("name")[:2], ["Equipos", "Materiales"])
        cameras = order.order_line.filtered(lambda l: l.product_id.product_tmpl_id in
                                            (self.bullet | self.dome))
        self.assertEqual(sum(cameras.mapped("product_uom_qty")), 4)
        bullet = cameras.filtered(lambda l: l.product_id.product_tmpl_id == self.bullet)
        # 300 × 1,20 = 360 (múltiplo de 5)
        self.assertEqual(bullet.price_unit, 360)
        self.assertEqual(bullet.mirabilenet_cot_cost, 300)
        self.assertFalse(bullet.tax_ids)
        self.assertEqual(order.mirabilenet_cot_total,
                         round(order.mirabilenet_cot_subtotal * 1.16, 2))
        self.assertGreater(order.mirabilenet_cot_profit, 0)
        self.assertIn("TB", order.mirabilenet_cot_storage)

    def test_prices_are_frozen(self):
        order = self._quote()
        line = order.order_line.filtered(lambda l: l.product_id.product_tmpl_id == self.bullet)
        self.bullet.standard_price = 999
        line.product_uom_qty = 3
        self.assertEqual(line.price_unit, 360)
        copy = order.copy()
        copied = copy.order_line.filtered(lambda l: l.product_id.product_tmpl_id == self.bullet)
        self.assertEqual(copied.price_unit, 360)
        self.assertNotEqual(copy.name, order.name)
        self.assertTrue(copy.name.startswith("COT-"))
        self.assertEqual(copy.mirabilenet_cot_stage, "borrador")

    def test_manual_markup_within_limits(self):
        order = self._quote()
        line = order.order_line.filtered(lambda l: l.product_id.product_tmpl_id == self.bullet)
        line.mirabilenet_cot_markup = 50
        self.assertEqual(line.price_unit, 450)
        with self.assertRaises(UserError):
            line.mirabilenet_cot_markup = 90

    def test_stages(self):
        order = self._quote()
        order.action_mirabilenet_cot_approve()
        self.assertEqual(order.mirabilenet_cot_stage, "aprobada")
        line = order.order_line.filtered(lambda l: not l.display_type)[:1]
        with self.assertRaises(UserError):
            line.product_uom_qty = 10
        order.action_mirabilenet_cot_mark_sent()
        old_validity = order.validity_date
        order.action_mirabilenet_cot_renew()
        self.assertGreaterEqual(order.validity_date, old_validity)
        order.action_mirabilenet_cot_won()
        self.assertEqual(order.mirabilenet_cot_stage, "ganada")
        self.assertEqual(order.state, "sale")
        with self.assertRaises(UserError):
            order.action_mirabilenet_cot_lost()

    def test_pdf_has_no_internal_data(self):
        order = self._quote(title="Casa de prueba")
        order.mirabilenet_cot_notes = "NOTA-INTERNA-SECRETA"
        html = self.env["ir.actions.report"]._render_qweb_html(
            "mirabilenet_cotizador.action_report_mirabilenet_cot", order.ids)[0].decode()
        self.assertIn(order.name, html)
        self.assertIn("Casa de prueba", html)
        self.assertIn("BORRADOR", html)
        for secret in ("NOTA-INTERNA-SECRETA", "Recargo", "Costo", "Ganancia", "stock", "T-CAM-B 300"):
            self.assertNotIn(secret, html, secret)
        self.assertNotIn(order.mirabilenet_cot_fmt(order.mirabilenet_cot_profit), html)
        order.action_mirabilenet_cot_approve()
        html = self.env["ir.actions.report"]._render_qweb_html(
            "mirabilenet_cotizador.action_report_mirabilenet_cot", order.ids)[0].decode()
        self.assertNotIn("BORRADOR", html)
        # En pruebas Odoo devuelve el HTML en vez del PDF (no necesita wkhtmltopdf).
        pdf, name = order._mirabilenet_cot_pdf()
        self.assertTrue(pdf)
        self.assertTrue(name.endswith(".pdf"))

    def test_from_text_and_products(self):
        order = self.Engine.create_from_text("4 cámaras para mi casa, 2 afuera, 15 días",
                                             "La Paz", self.partner)
        self.assertEqual(sum(order.order_line.filtered(
            lambda l: l.product_id.product_tmpl_id in (self.bullet | self.dome)).mapped(
            "product_uom_qty")), 4)
        self.assertIn("Pedido:", order.mirabilenet_cot_notes)
        loose = self.Engine.create_from_products([(self.dome, 2)], "El Alto", self.partner)
        line = loose.order_line.filtered(lambda l: not l.display_type)
        self.assertEqual(line.price_unit, 340)  # 280 × 1,20 = 336 → 340
        self.assertFalse(line.mirabilenet_cot_alerts)
        short = self.Engine.create_from_products([(self.dome, 9)], "El Alto", self.partner)
        self.assertIn("Sin stock", short.order_line.filtered(
            lambda l: not l.display_type).mirabilenet_cot_alerts)
        with self.assertRaises(UserError):
            self.Engine.create_from_text("hola", "La Paz", self.partner)

    def test_catalog_price(self):
        self.assertEqual(self.dome.mirabilenet_cot_price, 340)
        self.assertEqual(self.dome.mirabilenet_cot_price_invoiced, 394.4)
