from odoo import api, fields, models


class ProductTemplate(models.Model):
    """El artículo de inventario es el producto de Odoo: SKU = referencia interna,
    costo = costo estándar, serializado = seguimiento por número de serie."""
    _inherit = "product.template"

    mirabilenet_brand = fields.Char(string="Marca")
    mirabilenet_model = fields.Char(string="Modelo")
    mirabilenet_stock_min = fields.Float(
        string="Existencia mínima", help="Por debajo de esta cantidad se marca para reponer.")
    mirabilenet_below_min = fields.Boolean(
        string="Bajo el mínimo", compute="_compute_mirabilenet_below_min",
        search="_search_mirabilenet_below_min")

    @api.depends("mirabilenet_stock_min", "qty_available")
    def _compute_mirabilenet_below_min(self):
        for template in self:
            template.mirabilenet_below_min = bool(
                template.is_storable and template.mirabilenet_stock_min > 0
                and template.qty_available < template.mirabilenet_stock_min)

    def _search_mirabilenet_below_min(self, operator, value):
        truthy = any(value) if isinstance(value, (list, tuple, set)) else bool(value)
        positive = truthy if operator in ("=", "in") else not truthy
        candidates = self.search(
            [("is_storable", "=", True), ("mirabilenet_stock_min", ">", 0)])
        ids = candidates.filtered("mirabilenet_below_min").ids
        return [("id", "in" if positive else "not in", ids)]
