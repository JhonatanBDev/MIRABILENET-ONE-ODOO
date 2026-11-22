from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

from ..whatsapp.gateway import WhatsAppError
from ..whatsapp import cloud_api


class MirabilenetWhatsappNumber(models.Model):
    """Número de WhatsApp de una sucursal. Uno por sucursal: el remitente es determinista."""
    _name = "mirabilenet.whatsapp.number"
    _description = "MIRABILENET: número de WhatsApp de la sucursal"
    _inherit = ["mirabilenet.region.scoped"]
    _order = "branch_id"
    _rec_name = "display_number"
    _region_path = ("branch_id",)

    branch_id = fields.Many2one("mirabilenet.branch", string="Sucursal", required=True,
                                ondelete="cascade", index=True)
    region_id = fields.Many2one(related="branch_id.region_id", store=True, index=True)
    phone_number_id = fields.Char(string="Id del número en Meta", required=True)
    display_number = fields.Char(string="Número", required=True,
                                 help="En formato internacional, por ejemplo +59171006044.")
    sender_name = fields.Char(string="Nombre del remitente")
    active = fields.Boolean(string="Activo", default=True)
    shared_global = fields.Boolean(
        string="Compartido entre regiones",
        help="Remitente preferido para clientes de cualquier región. Solo puede haber uno. "
             "Compartir el remitente no comparte datos.")
    mode = fields.Selection(
        [("api_pura", "API pura"), ("coexistencia", "Coexistencia")], string="Modo de conexión",
        default="api_pura", required=True,
        help="API pura: el número vive solo en la nube. Coexistencia: sigue en la app de "
             "WhatsApp Business y la sucursal también escribe a mano.")
    verified_at = fields.Datetime(string="Verificado", readonly=True)
    meta_platform = fields.Char(string="Plataforma según Meta", readonly=True)
    last_error = fields.Char(string="Último error", readonly=True)

    _branch_uniq = models.Constraint("unique(branch_id)", "Esa sucursal ya tiene un número.")
    _pnid_uniq = models.Constraint("unique(phone_number_id)", "Ese número ya está registrado.")

    @api.constrains("display_number", "shared_global", "active")
    def _check_number(self):
        for number in self:
            if not (number.display_number or "").startswith("+"):
                raise ValidationError(_("El número debe empezar con + y el código de país."))
            if number.shared_global and self.sudo().search_count(
                    [("shared_global", "=", True), ("id", "!=", number.id)]):
                raise ValidationError(_("Ya existe un remitente compartido entre regiones."))

    def _check_shared_scope(self, vals):
        """Solo un usuario con alcance global activa o edita el remitente compartido."""
        if self.env.su:
            return
        user = self.env.user
        if user.mirabilenet_is_global or user._mirabilenet_is_super():
            return
        if vals.get("shared_global") or any(self.sudo().mapped("shared_global")):
            raise AccessError(_(
                "Solo un usuario con alcance global administra el remitente compartido."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_shared_scope(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._check_shared_scope(vals)
        return super().write(vals)

    def action_verify(self):
        """Comprueba con Meta que el token sirve y que el número es de esta cuenta."""
        self.check_access("write")
        Settings = self.env["mirabilenet.whatsapp.settings"]
        settings = Settings._load()
        for number in self.sudo():
            try:
                data = Settings._gateway().describe_number(
                    phone_number_id=number.phone_number_id,
                    token=settings._secret("access_token"), api_version=settings.api_version)
            except WhatsAppError as exc:
                number.last_error = str(exc)[:255]
                continue
            number.write({"verified_at": fields.Datetime.now(), "last_error": False,
                          "meta_platform": cloud_api.plataforma_de(data)})
        return True
