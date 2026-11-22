from odoo import api, fields, models


class MirabilenetWhatsappAgentActivity(models.Model):
    """Último mensaje que una persona de la sucursal mandó desde la app (coexistencia).

    Solo se guarda cuándo, no el texto: guardar el contenido sería quedarse con las
    conversaciones de la sucursal, que nadie pidió almacenar aquí.
    """
    _name = "mirabilenet.whatsapp.agent.activity"
    _description = "MIRABILENET: actividad de una persona en WhatsApp"
    _order = "last_message_at desc"
    _rec_name = "contact"

    number_id = fields.Many2one("mirabilenet.whatsapp.number", string="Número de la sucursal",
                                required=True, ondelete="cascade", index=True)
    region_id = fields.Many2one(related="number_id.region_id", store=True, index=True)
    contact = fields.Char(string="Contacto", required=True, index=True)
    partner_id = fields.Many2one("res.partner", string="Cliente", ondelete="set null")
    last_message_at = fields.Datetime(string="Último mensaje", required=True, index=True)

    _pair_uniq = models.Constraint(
        "unique(number_id, contact)", "Ya existe la actividad de ese contacto.")

    @api.model
    def _record_echo(self, number, contact, moment):
        Message = self.env["mirabilenet.whatsapp.message"]
        partner = Message._partner_by_number(contact)
        row = self.sudo().search(
            [("number_id", "=", number.id), ("contact", "=", contact)], limit=1)
        if not row:
            return self.sudo().create({"number_id": number.id, "contact": contact,
                                       "partner_id": partner.id, "last_message_at": moment})
        vals = {}
        if moment > row.last_message_at:
            vals["last_message_at"] = moment
        if partner and row.partner_id != partner:
            vals["partner_id"] = partner.id
        if vals:
            row.write(vals)
        return row
