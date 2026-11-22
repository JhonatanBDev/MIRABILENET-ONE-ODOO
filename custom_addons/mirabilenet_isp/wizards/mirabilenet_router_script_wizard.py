from odoo import fields, models


class MirabilenetRouterScriptWizard(models.TransientModel):
    """Muestra un guion generado para copiarlo al router. No guarda nada más."""
    _name = "mirabilenet.router.script.wizard"
    _description = "MIRABILENET: guion para el router"

    router_id = fields.Many2one("mirabilenet.router", string="Router", readonly=True)
    script = fields.Text(string="Guion", readonly=True)
    expires_at = fields.Datetime(string="El código vence", readonly=True)
