from odoo import fields, models

from .mirabilenet_web_published import ICONS


class MirabilenetWebAdvantage(models.Model):
    _name = "mirabilenet.web.advantage"
    _description = "MIRABILENET: ventaja del sitio"
    _inherit = ["mirabilenet.web.published"]
    _order = "sequence, id"
    _rec_name = "title"

    icon = fields.Selection(ICONS, string="Icono", default="escudo", required=True)
    title = fields.Char(string="Título", required=True, size=60)
    detail = fields.Char(string="Detalle", size=140)
    sequence = fields.Integer(string="Orden", default=0)
    active = fields.Boolean(string="Visible", default=True)
