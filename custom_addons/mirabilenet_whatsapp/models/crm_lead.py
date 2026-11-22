from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    mirabilenet_region_id = fields.Many2one("mirabilenet.region", string="Región",
                                            ondelete="set null", index=True)
    mirabilenet_origin = fields.Char(string="Origen de la consulta", index=True, readonly=True)
    mirabilenet_plan_interest = fields.Char(string="Plan de interés")
    mirabilenet_internal_note = fields.Char(string="Nota interna")
