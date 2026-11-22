from odoo import fields, models


class PosSession(models.Model):
    _inherit = "pos.session"

    mirabilenet_region_id = fields.Many2one(related="config_id.mirabilenet_region_id",
                                            store=True, index=True, string="Región")
