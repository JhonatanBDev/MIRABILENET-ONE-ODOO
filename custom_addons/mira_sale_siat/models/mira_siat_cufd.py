from odoo import fields, models


class MiraSiatCufd(models.Model):
    _name = "mira.siat.cufd"
    _description = "Mira_Sale SIAT: CUFD"
    _order = "id desc"
    _rec_name = "valid_until"

    pos_id = fields.Many2one("mira.siat.pos", string="Punto de venta", required=True,
                             ondelete="restrict", index=True)
    company_id = fields.Many2one(related="pos_id.company_id", store=True, index=True)
    code_encrypted = fields.Char(required=True, groups="base.group_system")
    control_code_encrypted = fields.Char(required=True, groups="base.group_system")
    address = fields.Char(string="Dirección registrada")
    valid_from = fields.Datetime(string="Obtenido el", required=True)
    valid_until = fields.Datetime(string="Vigente hasta", required=True)
    active = fields.Boolean(default=True)

    def _code(self):
        self.ensure_one()
        return self.env["mira.siat.service"]._vault().decrypt(self.sudo().code_encrypted)

    def _control_code(self):
        self.ensure_one()
        return self.env["mira.siat.service"]._vault().decrypt(
            self.sudo().control_code_encrypted)
