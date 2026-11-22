from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command

ROLES = [
    ("superadmin", "Superadministrador"),
    ("gerencia", "Gerencia general"),
    ("admin_regional", "Administrador regional"),
    ("noc", "NOC"),
    ("tecnico", "Técnico"),
    ("finanzas", "Finanzas"),
    ("cajero", "Cajero"),
    ("cobrador", "Cobrador"),
    ("almacenista", "Almacenista"),
    ("vendedor", "Vendedor"),
    ("operador_camaras", "Operador de cámaras"),
    ("auditor", "Auditor"),
    ("pasante", "Pasante"),
]
#: Ven todas las regiones. Solo el superadministrador los otorga.
ROLES_GLOBALES = {"superadmin", "gerencia", "auditor"}
#: Entran a administrar usuarios.
ROLES_GESTION = {"superadmin", "gerencia", "admin_regional"}

#: Lo único que se puede fijar desde la administración de usuarios de MIRABILENET.
#: Deja fuera «group_ids» a propósito: los permisos salen del rol.
EDITABLE_FIELDS = {
    "name", "login", "email", "phone", "active",
    "mirabilenet_role", "mirabilenet_region_id", "mirabilenet_branch_id",
}
PERMISSION_FIELDS = ("mirabilenet_role", "mirabilenet_region_id", "active")


class ResUsers(models.Model):
    _inherit = "res.users"

    mirabilenet_role = fields.Selection(ROLES, string="Rol en MIRABILENET", index=True)
    mirabilenet_region_id = fields.Many2one(
        "mirabilenet.region", string="Región", ondelete="restrict", index=True,
        help="Vacío solo tiene sentido en roles de alcance global.")
    mirabilenet_branch_id = fields.Many2one(
        "mirabilenet.branch", string="Sucursal", ondelete="set null",
        domain="[('region_id', '=', mirabilenet_region_id)]")
    mirabilenet_is_global = fields.Boolean(
        string="Alcance global", compute="_compute_mirabilenet_is_global")

    @api.depends("mirabilenet_role")
    def _compute_mirabilenet_is_global(self):
        for user in self:
            # El administrador técnico de Odoo también ve todas las regiones: las reglas de
            # región de facturas, pagos y sucursales no deben dejarlo fuera.
            user.mirabilenet_is_global = (user.mirabilenet_role in ROLES_GLOBALES
                                          or user.has_group("base.group_system"))

    @api.constrains("mirabilenet_region_id", "mirabilenet_branch_id")
    def _check_mirabilenet_branch(self):
        for user in self:
            branch = user.mirabilenet_branch_id
            if branch and branch.region_id != user.mirabilenet_region_id:
                raise ValidationError(_("La sucursal no pertenece a la región del usuario."))

    # ------------------------------------------------------------------
    # Barreras de la administración de usuarios
    # ------------------------------------------------------------------
    def _mirabilenet_is_super(self):
        self.ensure_one()
        return self.mirabilenet_role == "superadmin" or self.has_group("base.group_system")

    def _mirabilenet_check_manage(self, vals, creating=False):
        """Quien administra usuarios podría darse cualquier permiso: aquí se impide."""
        actor = self.env.user
        is_super = actor._mirabilenet_is_super()
        if not is_super and actor.mirabilenet_role not in ROLES_GESTION:
            raise AccessError(_("Su rol no administra usuarios."))
        if actor in self:
            raise UserError(_(
                "Nadie se edita a sí mismo desde la administración de usuarios: ni el rol, "
                "ni la región, ni el estado."))
        targets = self.sudo()
        if not is_super:
            if vals.get("mirabilenet_role") in ROLES_GLOBALES:
                raise AccessError(_("Su rol no puede otorgar este rol."))
            if any(u.mirabilenet_role in ROLES_GLOBALES or u.has_group("base.group_system")
                   for u in targets):
                raise AccessError(_("Su rol no puede modificar a este usuario."))
        if not is_super and not actor.mirabilenet_is_global:
            region = actor.mirabilenet_region_id
            if not region:
                raise AccessError(_("Usted no tiene una región asignada."))
            if creating and not vals.get("mirabilenet_region_id"):
                raise AccessError(_("Solo un rol global puede crear usuarios sin región."))
            if "mirabilenet_region_id" in vals and vals["mirabilenet_region_id"] != region.id:
                raise AccessError(_("Solo puede asignar usuarios a su propia región."))
            if any(u.mirabilenet_region_id != region for u in targets):
                raise AccessError(_("Solo puede administrar usuarios de su región."))

    @api.model
    def _mirabilenet_clean_vals(self, vals):
        unknown = set(vals) - EDITABLE_FIELDS
        if unknown:
            raise AccessError(_(
                "Estos datos no se cambian desde aquí: %s", ", ".join(sorted(unknown))))
        return dict(vals)

    @api.model
    def mirabilenet_create_user(self, vals):
        """Alta de un usuario por quien administra usuarios, sin ser admin de Odoo."""
        vals = self._mirabilenet_clean_vals(vals)
        if not vals.get("mirabilenet_role"):
            raise UserError(_("Indique el rol del usuario."))
        self.browse()._mirabilenet_check_manage(vals, creating=True)
        return self.sudo().with_context(no_reset_password=True).create(vals)

    def mirabilenet_update_user(self, vals):
        vals = self._mirabilenet_clean_vals(vals)
        self._mirabilenet_check_manage(vals)
        return self.sudo().write(vals)

    def action_mirabilenet_invite(self):
        """Envía el correo para que la persona defina su propia contraseña."""
        self._mirabilenet_check_manage({})
        self.sudo().action_reset_password()
        return True

    # ------------------------------------------------------------------
    # Rol -> grupos, y auditoría
    # ------------------------------------------------------------------
    def _mirabilenet_sync_groups(self):
        role_groups = {
            role: self.env.ref("mirabilenet_base.group_role_%s" % role) for role, _l in ROLES}
        for user in self.sudo():
            wanted = role_groups.get(user.mirabilenet_role)
            commands = [Command.unlink(g.id) for g in role_groups.values() if g != wanted]
            if wanted:
                commands.append(Command.link(wanted.id))
            user.write({"group_ids": commands})

    def _mirabilenet_snapshot(self):
        return {
            user.id: {
                "mirabilenet_role": user.mirabilenet_role or False,
                "mirabilenet_region_id": user.mirabilenet_region_id.id,
                "active": user.active,
            } for user in self.sudo()}

    @api.model_create_multi
    def create(self, vals_list):
        managed = [vals for vals in vals_list if vals.get("mirabilenet_role")
                   or vals.get("mirabilenet_region_id")]
        if managed and not self.env.su:
            for vals in managed:
                self.browse()._mirabilenet_check_manage(vals, creating=True)
        users = super().create(vals_list)
        with_role = users.filtered("mirabilenet_role")
        if with_role:
            with_role._mirabilenet_sync_groups()
            for user in with_role:
                self.env["mirabilenet.audit.log"]._log(
                    "permisos",
                    "Usuario %s creado con rol %s" % (user.login, user.mirabilenet_role),
                    record=user, region=user.mirabilenet_region_id,
                    payload=user._mirabilenet_snapshot()[user.id])
        return users

    def write(self, vals):
        touches = set(vals) & {"mirabilenet_role", "mirabilenet_region_id",
                               "mirabilenet_branch_id"}
        if "active" in vals and any(self.sudo().mapped("mirabilenet_role")):
            touches.add("active")
        if not touches:
            return super().write(vals)
        if not self.env.su:
            self._mirabilenet_check_manage(vals)
        before = self._mirabilenet_snapshot()
        result = super().write(vals)
        if "mirabilenet_role" in vals:
            self._mirabilenet_sync_groups()
        after = self._mirabilenet_snapshot()
        for user in self.sudo():
            changes = {
                name: [before[user.id][name], after[user.id][name]]
                for name in PERMISSION_FIELDS if before[user.id][name] != after[user.id][name]}
            if changes:
                self.env["mirabilenet.audit.log"]._log(
                    "permisos", "Cambio de permisos de %s" % user.login,
                    record=user, region=user.mirabilenet_region_id, payload=changes)
        return result

    def unlink(self):
        if any(self.sudo().mapped("mirabilenet_role")):
            raise UserError(_("Los usuarios se desactivan, no se eliminan."))
        return super().unlink()

    # ------------------------------------------------------------------
    # Pantalla de usuarios
    # ------------------------------------------------------------------
    @api.model
    def action_mirabilenet_users(self):
        actor = self.env.user
        domain = [("mirabilenet_role", "!=", False)]
        if not actor._mirabilenet_is_super() and not actor.mirabilenet_is_global:
            domain.append(("mirabilenet_region_id", "=", actor.mirabilenet_region_id.id))
        return {
            "type": "ir.actions.act_window",
            "name": _("Usuarios"),
            "res_model": "res.users",
            "view_mode": "list,form",
            "views": [
                (self.env.ref("mirabilenet_base.view_mirabilenet_users_list").id, "list"),
                (self.env.ref("mirabilenet_base.view_mirabilenet_users_form").id, "form"),
            ],
            "domain": domain,
            "context": {"active_test": False},
        }

    def action_mirabilenet_edit(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Editar usuario"),
            "res_model": "mirabilenet.user.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_user_id": self.id},
        }
