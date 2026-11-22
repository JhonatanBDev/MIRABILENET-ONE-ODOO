from odoo import fields, models


class MirabilenetWhatsappProofRejectWizard(models.TransientModel):
    """Pide el motivo escrito del rechazo de un comprobante."""
    _name = "mirabilenet.whatsapp.proof.reject.wizard"
    _description = "MIRABILENET: rechazo de un comprobante"

    proof_id = fields.Many2one("mirabilenet.whatsapp.proof", required=True, readonly=True)
    reason = fields.Char(string="Motivo", required=True)

    def action_confirm(self):
        self.ensure_one()
        self.proof_id.action_reject(self.reason)
        return {"type": "ir.actions.act_window_close"}
