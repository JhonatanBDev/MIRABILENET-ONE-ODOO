from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from odoo.addons.mirabilenet_isp.isp import vault

from ..whatsapp.gateway import FakeMetaGateway, RealMetaGateway, WhatsAppError


class MirabilenetWhatsappSettings(models.Model):
    """Credenciales de Meta y política de envío. Un solo registro para toda la empresa."""
    _name = "mirabilenet.whatsapp.settings"
    _description = "MIRABILENET: ajustes de WhatsApp"

    name = fields.Char(default="Ajustes de WhatsApp", readonly=True)
    active_messaging = fields.Boolean(
        string="Mensajería activa", help="Con esto apagado nada sale, ni siquiera las pruebas.")
    test_mode = fields.Boolean(
        string="Modo de prueba", default=True,
        help="Encola y arma los mensajes pero no los entrega a Meta. Sirve para revisar los "
             "textos antes de escribir a clientes reales.")
    api_version = fields.Char(string="Versión de la API", default="v21.0", required=True)
    waba_id = fields.Char(string="Id de la cuenta WABA")
    app_id = fields.Char(string="Id de la aplicación")
    access_token = fields.Char(string="Token de acceso nuevo", compute="_compute_secrets",
                               inverse="_inverse_access_token")
    webhook_verify_token = fields.Char(
        string="Token de verificación del webhook nuevo", compute="_compute_secrets",
        inverse="_inverse_webhook_verify_token")
    app_secret = fields.Char(string="Secreto de la aplicación nuevo",
                             compute="_compute_secrets", inverse="_inverse_app_secret")
    access_token_enc = fields.Char(groups="base.group_system", copy=False)
    webhook_verify_token_enc = fields.Char(groups="base.group_system", copy=False)
    app_secret_enc = fields.Char(groups="base.group_system", copy=False)
    has_access_token = fields.Boolean(string="Token cargado", compute="_compute_has_secrets")
    has_app_secret = fields.Boolean(string="Secreto cargado", compute="_compute_has_secrets")
    has_verify_token = fields.Boolean(string="Token de verificación cargado",
                                      compute="_compute_has_secrets")
    configured = fields.Boolean(string="Configurado", compute="_compute_has_secrets")

    hour_start = fields.Float(string="No enviar antes de", default=8.0)
    hour_end = fields.Float(string="No enviar después de", default=20.0)
    reminder_days = fields.Integer(
        string="Días de anticipación del recordatorio", default=3)
    max_retries = fields.Integer(string="Reintentos máximos", default=3)
    daily_limit = fields.Integer(
        string="Mensajes por cliente y día", default=2,
        help="Corta los bucles de reintento que acosarían al cliente.")
    require_consent = fields.Boolean(
        string="Exigir consentimiento registrado por cliente", default=False,
        help="Apagado: todo cliente cuenta con consentimiento, porque al contratar el "
             "servicio se le informa que se le puede contactar. Encendido: solo se escribe "
             "a quien tenga un consentimiento registrado en Mensajería > Consentimientos.")
    silence_hours = fields.Integer(
        string="Horas de silencio tras una respuesta humana", default=24,
        help="Solo para números en coexistencia. Cero lo desactiva.")
    mora_interval_days = fields.Integer(
        string="Días entre recordatorios de mora", default=7)
    mora_max_reminders = fields.Integer(string="Máximo de recordatorios de mora", default=3)

    @api.model
    def _load(self):
        settings = self.sudo().search([], limit=1, order="id")
        return settings or self.sudo().create({})

    def _compute_secrets(self):
        for settings in self:
            settings.access_token = settings.webhook_verify_token = False
            settings.app_secret = False

    def _store_secret(self, name):
        for settings in self.filtered(name):
            try:
                settings.sudo()[name + "_enc"] = vault.encrypt(settings[name])
            except vault.VaultError as exc:
                raise UserError(str(exc))
        self.invalidate_recordset([name])

    def _inverse_access_token(self):
        self._store_secret("access_token")

    def _inverse_webhook_verify_token(self):
        self._store_secret("webhook_verify_token")

    def _inverse_app_secret(self):
        self._store_secret("app_secret")

    def _secret(self, name):
        self.ensure_one()
        try:
            return vault.decrypt(self.sudo()[name + "_enc"])
        except vault.VaultError as exc:
            raise WhatsAppError(str(exc))

    @api.depends("access_token_enc", "app_secret_enc", "webhook_verify_token_enc", "waba_id")
    def _compute_has_secrets(self):
        for settings in self.sudo():
            settings.has_access_token = bool(settings.access_token_enc)
            settings.has_app_secret = bool(settings.app_secret_enc)
            settings.has_verify_token = bool(settings.webhook_verify_token_enc)
            settings.configured = bool(settings.waba_id and settings.access_token_enc)

    @api.constrains("hour_start", "hour_end", "daily_limit", "max_retries",
                    "mora_interval_days", "mora_max_reminders")
    def _check_policy(self):
        for settings in self:
            if not 0 <= settings.hour_start < settings.hour_end <= 24:
                raise ValidationError(_("La hora de fin debe ser posterior a la de inicio."))
            if min(settings.daily_limit, settings.max_retries, settings.mora_interval_days,
                   settings.mora_max_reminders) < 1:
                raise ValidationError(_("Los topes y los intervalos deben ser al menos 1."))

    @api.model_create_multi
    def create(self, vals_list):
        if self.sudo().search_count([]):
            raise UserError(_("Los ajustes de WhatsApp son un solo registro."))
        return super().create(vals_list)

    def unlink(self):
        raise UserError(_("Los ajustes de WhatsApp no se eliminan."))

    def _in_window(self, moment=None):
        """¿La hora local cae dentro del horario en que se puede escribir?"""
        self.ensure_one()
        tz = self.env["ir.config_parameter"].sudo().get_param(
            "mirabilenet.timezone", "America/La_Paz")
        local = fields.Datetime.context_timestamp(
            self.with_context(tz=tz), moment or fields.Datetime.now())
        hour = local.hour + local.minute / 60.0
        return self.hour_start <= hour <= self.hour_end

    @api.model
    def _gateway(self):
        mode = self.env["ir.config_parameter"].sudo().get_param(
            "mirabilenet.meta_gateway", "real")
        return FakeMetaGateway() if mode == "fake" else RealMetaGateway()
