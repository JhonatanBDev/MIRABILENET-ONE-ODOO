from odoo import fields, models


class MirabilenetService(models.Model):
    _inherit = "mirabilenet.service"

    mirabilenet_pos_order_id = fields.Many2one("pos.order", string="Solicitado en la venta",
                                               readonly=True, copy=False, index=True,
                                               ondelete="set null")
