from odoo import api, fields, models


class MirabilenetUserWizard(models.TransientModel):
    """El alta y edición de usuarios suma los datos del personal: WhatsApp, zonas y jefe."""
    _inherit = "mirabilenet.user.wizard"

    staff_whatsapp = fields.Char(string="WhatsApp para avisos")
    staff_notify = fields.Boolean(string="Recibe avisos por WhatsApp", default=True)
    staff_zone_ids = fields.Many2many("mirabilenet.zone", string="Zonas que atiende",
                                      domain="[('region_id', '=', region_id)]")
    staff_supervisor_id = fields.Many2one("res.users", string="Jefe directo",
                                          domain="[('share', '=', False)]")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        user = self.env["res.users"].browse(values.get("user_id")).sudo()
        if user:
            values.update({
                "staff_whatsapp": user.mirabilenet_whatsapp,
                "staff_notify": user.mirabilenet_staff_notify,
                "staff_zone_ids": [(6, 0, user.mirabilenet_zone_ids.ids)],
                "staff_supervisor_id": user.mirabilenet_supervisor_id.id,
            })
        return values

    def action_save(self):
        result = super().action_save()
        user = self.user_id or self.env["res.users"].sudo().with_context(
            active_test=False).search([("login", "=", self.login)], limit=1)
        if user:
            # Las barreras de quién administra a quién ya se pasaron al guardar arriba.
            user.sudo().write({
                "mirabilenet_whatsapp": self.staff_whatsapp or False,
                "mirabilenet_staff_notify": self.staff_notify,
                "mirabilenet_zone_ids": [(6, 0, self.staff_zone_ids.ids)],
                "mirabilenet_supervisor_id": self.staff_supervisor_id.id,
            })
        return result
