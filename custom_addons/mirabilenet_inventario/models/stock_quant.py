from odoo import fields, models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    mirabilenet_region_id = fields.Many2one(
        related="location_id.warehouse_id.mirabilenet_region_id", store=True, index=True,
        string="Región")
