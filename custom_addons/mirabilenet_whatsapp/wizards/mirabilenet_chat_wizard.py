from odoo import fields, models


class MirabilenetChatWizard(models.TransientModel):
    """Responder como persona en una conversación, o simular un mensaje entrante."""
    _name = "mirabilenet.chat.wizard"
    _description = "MIRABILENET: responder o simular en una conversación"

    conversation_id = fields.Many2one("mirabilenet.conversation", string="Conversación",
                                      readonly=True)
    contact = fields.Char(string="Número del contacto")
    text = fields.Text(string="Mensaje", required=True)

    def action_reply(self):
        self.ensure_one()
        self.conversation_id._reply_as_person(self.text)
        return {"type": "ir.actions.act_window_close"}

    def action_simulate(self):
        self.ensure_one()
        conversation = self.env["mirabilenet.conversation"]._simulate_incoming(
            self.contact, self.text)
        return {"type": "ir.actions.act_window", "res_model": "mirabilenet.conversation",
                "res_id": conversation.id, "view_mode": "form"}
