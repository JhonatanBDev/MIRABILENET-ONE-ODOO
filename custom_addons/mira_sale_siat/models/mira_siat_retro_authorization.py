import datetime

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from ..siat import errors as siat_errors

BACKDATE_GROUP = "mira_sale_siat.group_mira_siat_backdate"
MAX_HOURS = 48


class MiraSiatRetroAuthorization(models.Model):
    """Ventana, con motivo y responsable, que habilita emitir con fecha anterior."""
    _name = "mira.siat.retro.authorization"
    _description = "Mira_Sale SIAT: autorización de fecha anterior"
    _order = "id desc"
    _rec_name = "reason"

    company_id = fields.Many2one("res.company", string="Empresa", required=True, index=True,
                                 default=lambda self: self.env.company)
    user_id = fields.Many2one("res.users", string="Abierta por", required=True, readonly=True,
                              default=lambda self: self.env.user)
    reason = fields.Char(string="Motivo", required=True)
    start_at = fields.Datetime(string="Desde", required=True, default=fields.Datetime.now)
    end_at = fields.Datetime(
        string="Hasta", required=True,
        default=lambda self: fields.Datetime.now() + datetime.timedelta(hours=4))
    is_current = fields.Boolean(string="Vigente", compute="_compute_is_current",
                                search="_search_is_current")
    invoice_ids = fields.One2many(
        "mira.siat.invoice", "retro_authorization_id", string="Documentos emitidos")
    invoice_count = fields.Integer(compute="_compute_invoice_count")

    @api.depends("start_at", "end_at")
    def _compute_is_current(self):
        now = fields.Datetime.now()
        for auth in self:
            auth.is_current = bool(auth.start_at and auth.end_at
                                   and auth.start_at <= now < auth.end_at)

    def _search_is_current(self, operator, value):
        now = fields.Datetime.now()
        truthy = any(value) if isinstance(value, (list, tuple, set)) else bool(value)
        positive = truthy if operator in ("=", "in") else not truthy
        if positive:
            return [("start_at", "<=", now), ("end_at", ">", now)]
        return ["|", ("start_at", ">", now), ("end_at", "<=", now)]

    @api.depends("invoice_ids")
    def _compute_invoice_count(self):
        for auth in self:
            auth.invoice_count = len(auth.invoice_ids)

    @api.constrains("start_at", "end_at")
    def _check_window(self):
        for auth in self:
            # Igualdad permitida: una autorización puede cerrarse al instante.
            if auth.end_at < auth.start_at:
                raise ValidationError(_("El fin no puede ser anterior al inicio."))
            if auth.end_at - auth.start_at > datetime.timedelta(hours=MAX_HOURS):
                raise ValidationError(_(
                    "Una autorización dura como máximo %s horas. Abra otra si hace falta.",
                    MAX_HOURS))

    @api.model_create_multi
    def create(self, vals_list):
        service = self.env["mira.siat.service"]
        service._require_group(BACKDATE_GROUP, "retro.open")
        records = super().create(vals_list)
        for auth in records:
            service._audit("retro.open", auth,
                           after={"reason": auth.reason, "until": str(auth.end_at)})
        return records

    def write(self, vals):
        if set(vals) - {"end_at"}:
            raise UserError(_("Una autorización solo se puede cerrar antes de tiempo."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Las autorizaciones no se eliminan: son parte de la auditoría."))

    def action_close(self):
        service = self.env["mira.siat.service"]
        service._require_group(BACKDATE_GROUP, "retro.close")
        now = fields.Datetime.now()
        for auth in self.filtered("is_current"):
            auth.write({"end_at": now})
            service._audit("retro.close", auth)
        return True

    @api.model
    def _current(self, company):
        return self.sudo().search(
            [("company_id", "=", company.id), ("is_current", "=", True)], limit=1)

    @api.model
    def _require(self, company, when):
        """Valida permiso, autorización vigente y antigüedad de la fecha."""
        if not self.env.su and not self.env.user.has_group(BACKDATE_GROUP):
            raise AccessError(_(
                "[%s] No tiene permiso para emitir con fecha anterior.", siat_errors.AUTH))
        auth = self._current(company)
        if not auth:
            raise UserError(_(
                "No hay una autorización vigente para emitir con fecha anterior."))
        limit = min(company.mira_siat_backdate_max_hours or MAX_HOURS, MAX_HOURS)
        if when < fields.Datetime.now() - datetime.timedelta(hours=limit):
            raise UserError(_(
                "La fecha es anterior al máximo permitido (%s horas). Para ventas más "
                "antiguas corresponde una factura manual con talonario CAFC.", limit))
        return auth
