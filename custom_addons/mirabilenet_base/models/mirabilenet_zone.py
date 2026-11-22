from odoo import fields, models


class MirabilenetZone(models.Model):
    _name = "mirabilenet.zone"
    _description = "MIRABILENET: zona"
    _inherit = ["mirabilenet.region.scoped"]
    _order = "name"

    region_id = fields.Many2one("mirabilenet.region", string="Región", required=True,
                                ondelete="restrict", index=True)
    code = fields.Char(string="Código", required=True, size=20)
    name = fields.Char(string="Nombre", required=True)
    sector = fields.Char(string="Sector o comunidad")
    active = fields.Boolean(string="Activa", default=True)
    node_ids = fields.One2many("mirabilenet.node", "zone_id", string="Nodos")

    _code_uniq = models.Constraint("unique(code)", "Ya existe una zona con ese código.")
