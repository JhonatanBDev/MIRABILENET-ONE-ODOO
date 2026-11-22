from odoo import fields, models


class MiraSiatBranch(models.Model):
    _name = "mira.siat.branch"
    _description = "Mira_Sale SIAT: sucursal"
    _order = "company_id, code"

    name = fields.Char(string="Nombre", required=True)
    company_id = fields.Many2one(
        "res.company", string="Empresa", required=True, index=True,
        default=lambda self: self.env.company)
    code = fields.Integer(string="Código SIAT", required=True,
                          help="Código de sucursal ante el SIN. 0 = casa matriz.")
    address = fields.Char(string="Dirección", required=True)
    municipality = fields.Char(string="Municipio", required=True, size=25)
    phone = fields.Char(string="Teléfono", size=25)
    active = fields.Boolean(default=True)
    pos_ids = fields.One2many("mira.siat.pos", "branch_id", string="Puntos de venta")

    _code_company_uniq = models.Constraint(
        "unique(company_id, code)",
        "Ya existe una sucursal con ese código para esta empresa.")
