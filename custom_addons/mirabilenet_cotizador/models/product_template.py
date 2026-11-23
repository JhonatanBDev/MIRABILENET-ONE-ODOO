from odoo import api, fields, models

from ..cotizador import precios


class ProductTemplate(models.Model):
    """Producto del catálogo del cotizador (CCTV, redes). El costo es el precio del proveedor
    (DigiCorp) en `standard_price`; el precio de venta lo calcula el motor, no la tarifa."""
    _inherit = "product.template"

    mirabilenet_cot_sku = fields.Char(string="SKU del proveedor", index=True, copy=False)
    mirabilenet_cot_category = fields.Char(
        string="Categoría del proveedor", index=True,
        help="Categoría de DigiCorp (nivel 2), por ejemplo CAMARAS IP. Con esto el producto "
             "entra al catálogo del cotizador.")
    mirabilenet_cot_subcategory = fields.Char(string="Subcategoría del proveedor")
    mirabilenet_cot_brand = fields.Char(string="Marca")
    mirabilenet_cot_cost_at = fields.Datetime(string="Costo actualizado el")
    mirabilenet_cot_stock = fields.Json(
        string="Stock del proveedor por ciudad",
        help="{ciudad: unidades}, sin contar el showroom. Lo llena el conector de DigiCorp. "
             "Vacío = sin verificar.")
    mirabilenet_cot_stock_total = fields.Integer(string="Stock del proveedor (total)")
    mirabilenet_cot_offer_bot = fields.Boolean(
        string="Ofrecer en el bot", help="El bot de WhatsApp puede mostrarlo y cotizarlo.")
    mirabilenet_cot_price = fields.Float(
        string="Precio de venta (cotizador)", compute="_compute_mirabilenet_cot_price",
        help="Costo con el recargo de su categoría y el redondeo, sin impuestos.")
    mirabilenet_cot_price_invoiced = fields.Float(
        string="Con factura", compute="_compute_mirabilenet_cot_price")

    @api.depends("standard_price", "mirabilenet_cot_category", "mirabilenet_cot_subcategory")
    def _compute_mirabilenet_cot_price(self):
        cfg = self.env["mirabilenet.cot.engine"]._config()
        for product in self:
            if not product.mirabilenet_cot_category or not product.standard_price:
                product.mirabilenet_cot_price = product.mirabilenet_cot_price_invoiced = 0
                continue
            cost = precios.D(product.standard_price)
            markup = precios.recargo_para(cfg, product.mirabilenet_cot_category,
                                          product.mirabilenet_cot_subcategory, cost)
            price = precios.precio_venta(cfg, cost, markup)
            product.mirabilenet_cot_price = float(price)
            product.mirabilenet_cot_price_invoiced = float(
                precios.calcular_impuestos(cfg, price, True).total)

    def _mirabilenet_cot_stock_in(self, city):
        """Stock del proveedor en la ciudad, o None si nunca se verificó."""
        self.ensure_one()
        stock = self.mirabilenet_cot_stock
        if not isinstance(stock, dict):
            return None
        return int(stock.get(city) or 0)
