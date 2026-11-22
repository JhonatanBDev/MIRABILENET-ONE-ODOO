from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    mirabilenet_equipment_ids = fields.One2many(
        "stock.lot", "mirabilenet_partner_id", string="Equipos instalados")
