from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    mirabilenet_region_id = fields.Many2one(
        "mirabilenet.region", string="Región", index=True, ondelete="restrict",
        compute="_compute_mirabilenet_region_id", store=True, readonly=False)

    @api.depends("partner_id")
    def _compute_mirabilenet_region_id(self):
        for payment in self:
            payment.mirabilenet_region_id = payment.partner_id.sudo().mirabilenet_region_id
