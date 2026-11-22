from odoo import api, fields, models
from odoo.exceptions import UserError

from ..isp import vault


class MirabilenetPppoeAccount(models.Model):
    """Cuenta PPPoE de un servicio."""
    _name = "mirabilenet.pppoe.account"
    _description = "MIRABILENET: cuenta PPPoE"
    _inherit = ["mirabilenet.region.scoped"]
    _order = "username"
    _rec_name = "username"
    _region_path = ("service_id",)

    service_id = fields.Many2one("mirabilenet.service", string="Servicio", required=True,
                                 ondelete="cascade", index=True)
    region_id = fields.Many2one(related="service_id.region_id", store=True, index=True)
    username = fields.Char(string="Usuario PPPoE", required=True, index=True)
    password = fields.Char(string="Contraseña nueva", compute="_compute_password",
                           inverse="_inverse_password",
                           help="Se guarda cifrada y no se vuelve a mostrar.")
    password_enc = fields.Char(string="Contraseña (cifrada)", copy=False,
                               groups="base.group_system")
    has_password = fields.Boolean(string="Con contraseña", compute="_compute_has_password")
    fixed_ip = fields.Char(string="IP fija")
    profile = fields.Char(string="Perfil aplicado", readonly=True)
    caller_id = fields.Char(string="MAC / caller id")
    enabled = fields.Boolean(string="Habilitado en el router", readonly=True)
    session_active = fields.Boolean(string="Sesión activa", readonly=True)
    last_ip = fields.Char(string="Última IP", readonly=True)
    last_seen = fields.Datetime(string="Último acceso", readonly=True)
    synced = fields.Boolean(
        string="Sincronizado con el router", readonly=True,
        help="Falso si la plataforma y el router difieren.")

    _service_uniq = models.Constraint(
        "unique(service_id)", "El servicio ya tiene una cuenta PPPoE.")
    _username_uniq = models.Constraint("unique(username)", "Ese usuario PPPoE ya existe.")
    _fixed_ip_uniq = models.Constraint("unique(fixed_ip)", "Esa IP fija ya está asignada.")

    def _compute_password(self):
        for account in self:
            account.password = False

    def _inverse_password(self):
        for account in self.filtered("password"):
            try:
                account.sudo().password_enc = vault.encrypt(account.password)
            except vault.VaultError as exc:
                raise UserError(str(exc))
        # La contraseña en claro no debe quedar ni en la caché del registro.
        self.invalidate_recordset(["password"])

    @api.depends("password_enc")
    def _compute_has_password(self):
        for account in self.sudo():
            account.has_password = bool(account.password_enc)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("fixed_ip"):
                vals["fixed_ip"] = False  # vacío como NULL: varias cuentas sin IP fija
        return super().create(vals_list)

    def write(self, vals):
        if "fixed_ip" in vals and not vals["fixed_ip"]:
            vals["fixed_ip"] = False
        return super().write(vals)
