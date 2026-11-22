from odoo import api, fields, models

from ..models.res_users import ROLES

USER_FIELDS = ("name", "login", "email", "phone", "active")


class MirabilenetUserWizard(models.TransientModel):
    """Alta y edición de usuarios para quien no es administrador de Odoo.

    Solo arma los datos: las barreras están en res.users.
    """
    _name = "mirabilenet.user.wizard"
    _description = "MIRABILENET: alta y edición de usuario"

    user_id = fields.Many2one("res.users", string="Usuario", readonly=True)
    name = fields.Char(string="Nombre", required=True)
    login = fields.Char(string="Usuario de ingreso", required=True)
    email = fields.Char(string="Correo")
    phone = fields.Char(string="Teléfono")
    active = fields.Boolean(string="Activo", default=True)
    role = fields.Selection(ROLES, string="Rol", required=True)
    region_id = fields.Many2one("mirabilenet.region", string="Región")
    branch_id = fields.Many2one("mirabilenet.branch", string="Sucursal",
                                domain="[('region_id', '=', region_id)]")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        user = self.env["res.users"].browse(values.get("user_id")).sudo()
        if user:
            values.update({name: user[name] for name in USER_FIELDS})
            values.update({
                "role": user.mirabilenet_role,
                "region_id": user.mirabilenet_region_id.id,
                "branch_id": user.mirabilenet_branch_id.id,
            })
        elif not self.env.user.mirabilenet_is_global:
            values["region_id"] = self.env.user.mirabilenet_region_id.id
        return values

    @api.onchange("region_id")
    def _onchange_region_id(self):
        if self.branch_id.region_id != self.region_id:
            self.branch_id = False

    def action_save(self):
        self.ensure_one()
        vals = {name: self[name] for name in USER_FIELDS}
        vals.update({
            "mirabilenet_role": self.role,
            "mirabilenet_region_id": self.region_id.id,
            "mirabilenet_branch_id": self.branch_id.id,
        })
        if self.user_id:
            self.user_id.mirabilenet_update_user(vals)
        else:
            self.env["res.users"].mirabilenet_create_user(vals)
        return {"type": "ir.actions.act_window_close"}
