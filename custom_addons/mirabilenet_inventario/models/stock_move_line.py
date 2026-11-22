from odoo import fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    mirabilenet_region_id = fields.Many2one(
        related="move_id.mirabilenet_region_id", store=True, index=True, string="Región")
