import logging
import uuid

from odoo import SUPERUSER_ID, api, fields, models, modules, _
from odoo.exceptions import UserError, ValidationError

from ..siat import errors as siat_errors
from ..siat.gateway import FakeSiatGateway, RealSiatGateway
from ..siat.soap_client import SiatSoapClient
from ..siat.vault import fingerprint

_logger = logging.getLogger(__name__)

# Campos de configuración tributaria cuyo cambio queda auditado.
_AUDITED = (
    "mira_siat_enabled", "mira_siat_environment", "mira_siat_modality",
    "mira_siat_system_code", "mira_siat_association_status", "mira_siat_gateway_mode",
    "mira_siat_package_size", "vat",
)


class ResCompany(models.Model):
    """Cada empresa de Odoo es un contribuyente (tenant) con su propio perfil
    tributario, token delegado, sucursales, puntos de venta y catálogos."""
    _inherit = "res.company"

    mira_siat_enabled = fields.Boolean(string="Facturación SIAT (Mira_Sale)")
    mira_siat_environment = fields.Selection(
        [("2", "PILOTO (pruebas)"), ("1", "PRODUCCIÓN")],
        string="Ambiente SIAT", default="2", required=True)
    mira_siat_modality = fields.Selection(
        [("2", "Computarizada en Línea"), ("1", "Electrónica en Línea")],
        string="Modalidad", default="2", required=True)
    mira_siat_system_code = fields.Char(
        string="Código de sistema",
        help="Código que el SIN asigna al Sistema Proveedor Mira_Sale.")
    mira_siat_association_status = fields.Selection(
        [("pending", "Pendiente de asociación"),
         ("associated", "Asociado al sistema proveedor"),
         ("suspended", "Suspendido")],
        string="Asociación SIAT", default="pending", required=True)
    mira_siat_gateway_mode = fields.Selection(
        [("fake", "Simulador (desarrollo)"), ("real", "SIAT real")],
        string="Conexión", default="fake", required=True,
        help="El simulador no habla con el SIN y sus documentos no tienen "
             "validez fiscal. Solo se admite en ambiente PILOTO.")
    mira_siat_package_size = fields.Integer(
        string="Facturas por paquete", default=500,
        help="Máximo de facturas por paquete de contingencia. Parametrizable: "
             "el SIN puede cambiar el límite.")
    mira_siat_currency_item_id = fields.Many2one(
        "mira.siat.catalog.item", string="Moneda SIAT de la empresa",
        domain="[('catalog_type', '=', 'tipo_moneda'), ('company_id', '=', id)]",
        help="Código del catálogo de monedas del SIN que corresponde a la "
             "moneda de la empresa.")
    mira_siat_default_payment_method_id = fields.Many2one(
        "mira.siat.catalog.item", string="Método de pago por defecto",
        domain="[('catalog_type', '=', 'tipo_metodo_pago'), ('company_id', '=', id)]")

    mira_siat_credit_payment_method_id = fields.Many2one(
        "mira.siat.catalog.item", string="Método de pago para ventas a crédito",
        domain="[('catalog_type', '=', 'tipo_metodo_pago'), ('company_id', '=', id)]",
        help="Método que se declara cuando la factura se emite antes de cobrarse "
             "(en el catálogo del SIN suele llamarse «PAGO POSTERIOR»).")
    mira_siat_default_unit_id = fields.Many2one(
        "mira.siat.catalog.item", string="Unidad de medida por defecto",
        domain="[('catalog_type', '=', 'unidad_medida'), ('company_id', '=', id)]",
        help="Se usa en los productos que no tienen unidad SIN propia.")
    mira_siat_activity_ids = fields.Many2many(
        "mira.siat.catalog.item", "mira_siat_company_activity_rel", "company_id", "item_id",
        string="Actividades económicas de la empresa",
        domain="[('catalog_type', '=', 'actividades'), ('company_id', '=', id)]",
        help="Si se indican, los productos solo pueden usar estas actividades.")
    mira_siat_default_sector = fields.Selection(
        [("1", "Factura de Compra y Venta"), ("22", "Factura de Telecomunicaciones")],
        string="Documento sector por defecto", default="1", required=True)
    mira_siat_backdate_max_hours = fields.Integer(
        string="Antigüedad máxima para fecha anterior (horas)", default=48)
    mira_siat_auto_email = fields.Boolean(
        string="Enviar la factura por correo al validarse", default=True)

    # Token delegado: cifrado, nunca legible desde la interfaz.
    mira_siat_token_encrypted = fields.Char(copy=False, groups="base.group_system")
    mira_siat_token_fingerprint = fields.Char(
        string="Huella del token", copy=False, readonly=True)
    mira_siat_token_expires_at = fields.Datetime(
        string="Vencimiento del token", copy=False, readonly=True)
    mira_siat_token_state = fields.Selection(
        [("missing", "Sin token"), ("valid", "Vigente"), ("expired", "Vencido")],
        string="Estado del token", compute="_compute_mira_siat_token_state")

    @api.depends("mira_siat_token_fingerprint", "mira_siat_token_expires_at")
    def _compute_mira_siat_token_state(self):
        now = fields.Datetime.now()
        for company in self:
            if not company.mira_siat_token_fingerprint:
                company.mira_siat_token_state = "missing"
            elif company.mira_siat_token_expires_at and company.mira_siat_token_expires_at <= now:
                company.mira_siat_token_state = "expired"
            else:
                company.mira_siat_token_state = "valid"

    @api.constrains("mira_siat_environment", "mira_siat_gateway_mode")
    def _check_mira_siat_fake_only_pilot(self):
        for company in self:
            if company.mira_siat_environment == "1" and company.mira_siat_gateway_mode == "fake":
                raise ValidationError(_(
                    "El simulador no puede usarse en ambiente de PRODUCCIÓN."))

    @api.constrains("mira_siat_package_size", "mira_siat_backdate_max_hours")
    def _check_mira_siat_package_size(self):
        for company in self:
            if company.mira_siat_package_size < 1:
                raise ValidationError(_("El tamaño de paquete debe ser al menos 1."))
            if not 1 <= company.mira_siat_backdate_max_hours <= 48:
                raise ValidationError(_(
                    "La antigüedad máxima para emitir con fecha anterior debe estar "
                    "entre 1 y 48 horas."))

    def _mira_siat_default_pos(self):
        """Punto de venta por defecto: el marcado, o el único que exista."""
        self.ensure_one()
        points = self.env["mira.siat.pos"].search(
            [("company_id", "=", self.id), ("code", ">=", 0)])
        return points.filtered("is_default")[:1] or (points if len(points) == 1 else points[:0])

    def write(self, vals):
        audited = [f for f in _AUDITED if f in vals]
        before = {c.id: {f: c[f] for f in audited} for c in self} if audited else {}
        res = super().write(vals)
        if audited:
            service = self.env["mira.siat.service"]
            for company in self:
                after = {f: company[f] for f in audited}
                if after != before[company.id]:
                    service._audit("config.company", company, before[company.id],
                                   after, company=company)
        return res

    # ---- token ------------------------------------------------------------
    def _mira_siat_set_token(self, token, expires_at):
        self.ensure_one()
        service = self.env["mira.siat.service"]
        service._require_group("mira_sale_siat.group_mira_siat_manager", "token.set")
        token = (token or "").strip()
        if not token:
            raise UserError(_("El token delegado está vacío."))
        try:
            encrypted = service._vault().encrypt(token)
        except siat_errors.SiatError as exc:
            raise service._user_error(exc)
        before = {"fingerprint": self.mira_siat_token_fingerprint}
        self.sudo().write({
            "mira_siat_token_encrypted": encrypted,
            "mira_siat_token_fingerprint": fingerprint(token),
            "mira_siat_token_expires_at": expires_at,
        })
        service._audit("token.set", self, before,
                       {"fingerprint": self.mira_siat_token_fingerprint}, company=self)

    def _mira_siat_token(self):
        """Token en claro, solo en memoria y solo para firmar la llamada."""
        self.ensure_one()
        company = self.sudo()
        if not company.mira_siat_token_encrypted or company.mira_siat_token_state != "valid":
            raise siat_errors.SiatError(siat_errors.TOKEN)
        return self.env["mira.siat.service"]._vault().decrypt(
            company.mira_siat_token_encrypted)

    # ---- acceso al SIAT ---------------------------------------------------
    def _mira_siat_check_active(self):
        self.ensure_one()
        if not self.mira_siat_enabled:
            raise siat_errors.SiatError(
                siat_errors.TENANT, "La empresa no tiene habilitada la facturación SIAT.")
        if self.mira_siat_association_status != "associated":
            raise siat_errors.SiatError(
                siat_errors.TENANT,
                "La empresa no está asociada al sistema proveedor (o está suspendida).")
        if not (self.vat or "").strip().isdigit():
            raise siat_errors.SiatError(
                siat_errors.TENANT, "La empresa no tiene un NIT numérico configurado.")
        if self.mira_siat_gateway_mode == "real" and not self.mira_siat_system_code:
            raise siat_errors.SiatError(
                siat_errors.TENANT, "Falta el código de sistema asignado por el SIN.")

    def _mira_siat_exchange_logger(self, correlation_id):
        company_id = self.id
        uid = self.env.uid
        env = self.env

        def on_exchange(vals):
            vals = dict(vals, company_id=company_id, user_id=uid,
                        correlation_id=correlation_id or False)
            if modules.module.current_test:
                env["mira.siat.log"].sudo().create(vals)
                return
            # Cursor propio: la evidencia sobrevive aunque la operación se revierta.
            try:
                with env.registry.cursor() as cr:
                    api.Environment(cr, SUPERUSER_ID, {})["mira.siat.log"].create(vals)
            except Exception:
                _logger.exception("No se pudo guardar la evidencia técnica SIAT")
        return on_exchange

    def _mira_siat_gateway(self, correlation_id=None):
        """Devuelve la implementación de SiatGateway de esta empresa."""
        self.ensure_one()
        logger = self._mira_siat_exchange_logger(correlation_id or str(uuid.uuid4()))
        if self.mira_siat_gateway_mode == "fake":
            return FakeSiatGateway(on_exchange=logger)
        params = self.env["ir.config_parameter"].sudo()
        base_url = params.get_param("mira_siat.ws_url.%s" % self.mira_siat_environment)
        if not base_url:
            raise siat_errors.SiatError(
                siat_errors.TENANT, "No está configurada la URL de servicios del SIAT.")
        client = SiatSoapClient(
            base_url, self._mira_siat_token(),
            connect_timeout=float(params.get_param("mira_siat.connect_timeout", "5")),
            read_timeout=float(params.get_param("mira_siat.read_timeout", "30")),
            on_exchange=logger)
        return RealSiatGateway(client)

    def _mira_siat_qr_base_url(self):
        self.ensure_one()
        return self.env["ir.config_parameter"].sudo().get_param(
            "mira_siat.qr_url.%s" % self.mira_siat_environment) or ""

    # ---- acciones ---------------------------------------------------------
    def action_mira_siat_token_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Configurar token delegado"),
            "res_model": "mira.siat.token.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_company_id": self.id},
        }

    # ---- tareas programadas ----------------------------------------------
    @api.model
    def _cron_mira_siat_renew_cufd(self):
        """Renueva el CUFD de cada punto de venta activo."""
        points = self.env["mira.siat.pos"].search([
            ("company_id.mira_siat_enabled", "=", True),
            ("company_id.mira_siat_association_status", "=", "associated"),
        ])
        for pos in points:
            try:
                pos._renew_cufd()
                self.env["mira.siat.service"]._commit()
            except siat_errors.SiatError as exc:
                _logger.warning("CUFD no renovado para %s: %s", pos.display_name, exc)

    @api.model
    def _cron_mira_siat_retry_pending(self):
        """Consulta el estado de los documentos sin respuesta y los concilia."""
        invoices = self.env["mira.siat.invoice"].search(
            [("state", "in", ("pending_retry", "issuing", "sent"))], limit=200)
        for invoice in invoices:
            invoice._retry()
            self.env["mira.siat.service"]._commit()
