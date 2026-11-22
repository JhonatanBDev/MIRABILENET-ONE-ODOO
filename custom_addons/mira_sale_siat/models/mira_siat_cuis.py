from odoo import fields, models


class MiraSiatCuis(models.Model):
    _name = "mira.siat.cuis"
    _description = "Mira_Sale SIAT: CUIS"
    _order = "id desc"
    _rec_name = "valid_until"

    pos_id = fields.Many2one("mira.siat.pos", string="Punto de venta", required=True,
                             ondelete="restrict", index=True)
    company_id = fields.Many2one(related="pos_id.company_id", store=True, index=True)
    code_encrypted = fields.Char(required=True, groups="base.group_system")
    valid_until = fields.Datetime(string="Vigente hasta", required=True)
    active = fields.Boolean(default=True)

    def _code(self):
        self.ensure_one()
        return self.env["mira.siat.service"]._vault().decrypt(self.sudo().code_encrypted)
