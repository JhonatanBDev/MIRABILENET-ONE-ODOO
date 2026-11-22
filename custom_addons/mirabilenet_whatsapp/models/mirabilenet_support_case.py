from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

OPERATOR = "mirabilenet_whatsapp.group_mirabilenet_whatsapp_operator"


class MirabilenetSupportCase(models.Model):
    """Solicitud de un cliente para que lo atienda una persona, o para darse de baja."""
    _name = "mirabilenet.support.case"
    _description = "MIRABILENET: solicitud de atención"
    _order = "state, id desc"
    _rec_name = "partner_id"

    partner_id = fields.Many2one("res.partner", string="Cliente", required=True,
                                 ondelete="restrict", index=True, readonly=True)
    region_id = fields.Many2one(related="partner_id.mirabilenet_region_id", store=True,
                                index=True, string="Región")
    kind = fields.Selection(
        [("ayuda", "Ayuda"), ("baja_servicio", "Solicitud de baja del servicio")],
        string="Tipo", required=True, readonly=True)
    reason = fields.Text(string="Motivo declarado", readonly=True)
    state = fields.Selection(
        [("nuevo", "Nuevo"), ("atencion", "En atención"), ("resuelto", "Resuelto")],
        string="Estado", default="nuevo", required=True, index=True, readonly=True)
    assigned_to = fields.Many2one("res.users", string="Asignado a", readonly=True)
    inbound_message_id = fields.Char(string="Id del mensaje entrante", readonly=True,
                                     index=True)
    conversation_id = fields.Many2one("mirabilenet.conversation", string="Conversación",
                                      ondelete="set null", readonly=True)
    resolved_at = fields.Datetime(string="Resuelto el", readonly=True)

    _inbound_uniq = models.Constraint(
        "unique(inbound_message_id)", "Esa solicitud ya fue registrada.")

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise UserError(_("Las solicitudes llegan desde las conversaciones."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise UserError(_("Una solicitud se toma o se resuelve con sus acciones."))
        return super().write(vals)

    def _require_operator(self):
        if not self.env.su and not self.env.user.has_group(OPERATOR):
            raise AccessError(_("Su rol no atiende solicitudes."))
        self.check_access("read")

    def action_take(self):
        self._require_operator()
        for case in self.sudo().filtered(lambda c: c.state == "nuevo"):
            case.write({"state": "atencion", "assigned_to": self.env.uid})
            case.conversation_id.write({"state": "humano", "attended_by": self.env.uid})
        return True

    def action_resolve(self):
        """Al resolver, la conversación vuelve al asistente."""
        self._require_operator()
        for case in self.sudo().filtered(lambda c: c.state != "resuelto"):
            case.write({"state": "resuelto", "resolved_at": fields.Datetime.now(),
                        "assigned_to": case.assigned_to.id or self.env.uid})
            if case.conversation_id and not self.sudo().search_count(
                    [("conversation_id", "=", case.conversation_id.id),
                     ("state", "in", ("nuevo", "atencion"))]):
                case.conversation_id._return_to_bot()
        return True
