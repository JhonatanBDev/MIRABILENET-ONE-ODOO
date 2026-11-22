from odoo import fields, models


class MiraSiatTokenWizard(models.TransientModel):
    """Captura el token delegado. Se cifra al guardar y no vuelve a mostrarse."""
    _name = "mira.siat.token.wizard"
    _description = "Mira_Sale SIAT: configurar token delegado"

    company_id = fields.Many2one("res.company", string="Empresa", required=True,
                                 default=lambda self: self.env.company)
    token = fields.Char(string="Token delegado", required=True)
    expires_at = fields.Datetime(string="Vence el", required=True)

    def action_save(self):
        self.ensure_one()
        self.company_id._mira_siat_set_token(self.token, self.expires_at)
        # El token no debe quedar en la tabla temporal del asistente.
        self.sudo().write({"token": "***"})
        return {"type": "ir.actions.act_window_close"}
