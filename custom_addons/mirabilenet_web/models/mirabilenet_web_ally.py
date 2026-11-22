from odoo import fields, models


class MirabilenetWebPartner(models.Model):
    _name = "mirabilenet.web.ally"
    _description = "MIRABILENET: tecnología o aliado del sitio"
    _inherit = ["mirabilenet.web.published"]
    _order = "sequence, id"

    name = fields.Char(string="Nombre", required=True, size=60)
    detail = fields.Char(string="Detalle", size=80)
    sequence = fields.Integer(string="Orden", default=0)
    active = fields.Boolean(string="Visible", default=True)
