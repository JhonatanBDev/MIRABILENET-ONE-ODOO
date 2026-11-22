from odoo import api, fields, models


class MirabilenetBranch(models.Model):
    _name = "mirabilenet.branch"
    _description = "MIRABILENET: sucursal"
    _inherit = ["mirabilenet.region.scoped"]
    _order = "name"

    region_id = fields.Many2one("mirabilenet.region", string="Región", required=True,
                                ondelete="restrict", index=True)
    code = fields.Char(string="Código", required=True, size=20)
    name = fields.Char(string="Nombre", required=True)
    address = fields.Char(string="Dirección")
    phone = fields.Char(string="Teléfono")
    active = fields.Boolean(string="Activa", default=True)

    _code_uniq = models.Constraint("unique(code)", "Ya existe una sucursal con ese código.")

    @api.depends("name", "region_id.name")
    def _compute_display_name(self):
        for branch in self:
            branch.display_name = "%s (%s)" % (branch.name, branch.region_id.name)
