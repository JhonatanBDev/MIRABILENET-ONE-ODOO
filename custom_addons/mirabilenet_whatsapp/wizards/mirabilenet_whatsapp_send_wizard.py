from odoo import fields, models

from ..models.mirabilenet_whatsapp_template import EVENTS
from ..models.mirabilenet_whatsapp_message import MANUAL_EVENTS


class MirabilenetWhatsappSendWizard(models.TransientModel):
    """Envío manual de un aviso de cobro. Las reglas están en el mensaje."""
    _name = "mirabilenet.whatsapp.send.wizard"
    _description = "MIRABILENET: envío manual por WhatsApp"

    partner_id = fields.Many2one(
        "res.partner", string="Cliente", required=True,
        domain="[('mirabilenet_is_customer', '=', True)]")
    charge_id = fields.Many2one(
        "account.move", string="Aviso de cobro", required=True,
        domain="[('partner_id', '=', partner_id), ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial'))]")
    event = fields.Selection([e for e in EVENTS if e[0] in MANUAL_EVENTS], string="Aviso",
                             required=True, default="recordatorio_pago")

    def action_send(self):
        self.ensure_one()
        message = self.env["mirabilenet.whatsapp.message"]._send_manual(
            self.charge_id, self.event)
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"type": "success" if message.state == "enviado" else "warning",
                       "message": dict(message._fields["state"].selection)[message.state],
                       "next": {"type": "ir.actions.act_window_close"}},
        }
