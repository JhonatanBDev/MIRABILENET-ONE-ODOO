from odoo import fields, models

COVERAGE_STATES = [("disponible", "Cobertura disponible"), ("parcial", "Cobertura parcial"),
                   ("proximamente", "Próximamente")]


class MirabilenetWebCoverage(models.Model):
    """Localidad con cobertura. Es el único dato que puede decir «parcial» o «próximamente»."""
    _name = "mirabilenet.web.coverage"
    _description = "MIRABILENET: localidad con cobertura"
    _inherit = ["mirabilenet.web.published", "mirabilenet.region.scoped"]
    _order = "region_id, sequence, name"

    region_id = fields.Many2one("mirabilenet.region", string="Región", required=True,
                                ondelete="restrict", index=True)
    name = fields.Char(string="Localidad", required=True, size=100)
    detail = fields.Char(string="Detalle", size=160)
    state = fields.Selection(COVERAGE_STATES, string="Estado", default="disponible",
                             required=True)
    sequence = fields.Integer(string="Orden", default=0)
    active = fields.Boolean(string="Visible", default=True)
