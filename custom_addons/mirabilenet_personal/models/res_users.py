from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.mirabilenet_whatsapp.whatsapp import phones

#: Roles que reciben y atienden averías de campo.
FIELD_ROLES = ("tecnico",)
#: Roles que supervisan a los técnicos de su región cuando nadie más está asignado.
SUPERVISOR_ROLES = ("admin_regional", "noc")


class ResUsers(models.Model):
    _inherit = "res.users"

    mirabilenet_whatsapp = fields.Char(
        string="WhatsApp del personal", copy=False, index=True,
        help="Número al que le llegan sus avisos de trabajo (averías, tareas). Se guarda con "
             "el código del país: 59171234567.")
    mirabilenet_staff_notify = fields.Boolean(
        string="Recibe avisos por WhatsApp", default=True)
    mirabilenet_zone_ids = fields.Many2many(
        "mirabilenet.zone", "mirabilenet_user_zone_rel", "user_id", "zone_id",
        string="Zonas que atiende",
        help="Las averías de clientes de estas zonas se le asignan automáticamente.")
    mirabilenet_supervisor_id = fields.Many2one(
        "res.users", string="Jefe directo", ondelete="set null",
        help="Recibe los avisos de averías que no se pudieron resolver o que no se atendieron.")

    @api.constrains("mirabilenet_whatsapp")
    def _check_mirabilenet_whatsapp(self):
        for user in self.filtered("mirabilenet_whatsapp"):
            other = self.sudo().search([("mirabilenet_whatsapp", "=", user.mirabilenet_whatsapp),
                                        ("id", "!=", user.id)], limit=1)
            if other:
                raise ValidationError(_("Ese WhatsApp ya es de %s.", other.name))

    @api.model
    def _mirabilenet_normalize_whatsapp(self, raw):
        if not raw:
            return False
        try:
            return phones.normalize_number(raw)
        except phones.NotSendable as exc:
            raise ValidationError(_("WhatsApp no válido: %s", raw)) from exc

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("mirabilenet_whatsapp"):
                vals["mirabilenet_whatsapp"] = self._mirabilenet_normalize_whatsapp(
                    vals["mirabilenet_whatsapp"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("mirabilenet_whatsapp"):
            vals = dict(vals, mirabilenet_whatsapp=self._mirabilenet_normalize_whatsapp(
                vals["mirabilenet_whatsapp"]))
        return super().write(vals)

    # ------------------------------------------------------------------
    @api.model
    def _mirabilenet_staff_by_number(self, number):
        """El usuario activo del personal que tiene ese WhatsApp (ya normalizado)."""
        if not number:
            return self.browse()
        return self.sudo().search([("mirabilenet_whatsapp", "=", number),
                                   ("share", "=", False)], limit=1)

    def _mirabilenet_reachable(self):
        """Los que tienen WhatsApp y aceptan avisos."""
        return self.filtered(lambda u: u.active and u.mirabilenet_whatsapp
                             and u.mirabilenet_staff_notify)

    def _mirabilenet_supervisors(self):
        """A quién se le avisa por este usuario: su jefe, o los encargados de su región."""
        self.ensure_one()
        if self.mirabilenet_supervisor_id._mirabilenet_reachable():
            return self.mirabilenet_supervisor_id
        return self._mirabilenet_region_supervisors(self.mirabilenet_region_id) - self

    @api.model
    def _mirabilenet_region_supervisors(self, region):
        if not region:
            return self.browse()
        return self.sudo().search([("mirabilenet_role", "in", SUPERVISOR_ROLES),
                                   ("mirabilenet_region_id", "=", region.id)])._mirabilenet_reachable()
