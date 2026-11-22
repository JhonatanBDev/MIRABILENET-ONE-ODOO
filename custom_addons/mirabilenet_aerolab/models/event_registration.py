from odoo import fields, models


class EventRegistration(models.Model):
    _inherit = "event.registration"

    mirabilenet_region_id = fields.Many2one(related="event_id.mirabilenet_region_id",
                                            store=True, index=True, string="Región")
