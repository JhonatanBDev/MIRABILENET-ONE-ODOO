from odoo import fields, models

from .mirabilenet_web_published import ICONS


class MirabilenetWebFigure(models.Model):
    """Cifra de la portada. Solo datos reales: no se inventan."""
    _name = "mirabilenet.web.figure"
    _description = "MIRABILENET: cifra del sitio"
    _inherit = ["mirabilenet.web.published"]
    _order = "sequence, id"
    _rec_name = "label"

    icon = fields.Selection(ICONS, string="Icono", default="personas", required=True)
    value = fields.Char(string="Valor", required=True, size=20)
    label = fields.Char(string="Etiqueta", required=True, size=60)
    sequence = fields.Integer(string="Orden", default=0)
    active = fields.Boolean(string="Visible", default=True)
