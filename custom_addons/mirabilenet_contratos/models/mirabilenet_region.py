from datetime import timedelta

from odoo import api, fields, models

from .account_move import OPEN_PAYMENT_STATES

DEFAULT_TZ = "America/La_Paz"


class MirabilenetRegion(models.Model):
    _inherit = "mirabilenet.region"

    @api.model
    def _cron_scheduled_cuts(self, hour=None, today=None):
        """A la hora de corte de cada región, pide suspender los servicios con facturas
        vencidas hace más días que los días de gracia de esa región."""
        today = today or fields.Date.context_today(self)
        if hour is None:
            tz = self.env["ir.config_parameter"].sudo().get_param(
                "mirabilenet.timezone", DEFAULT_TZ)
            hour = fields.Datetime.context_timestamp(
                self.with_context(tz=tz), fields.Datetime.now()).hour
        total = 0
        regions = self.sudo().search([("suspension_automatica", "=", True)])
        for region in regions.filtered(lambda r: int(r.hora_corte) == hour):
            limit = today - timedelta(days=max(region.dias_gracia, 0))
            overdue = self.env["account.move"].sudo().search([
                ("mirabilenet_region_id", "=", region.id), ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"), ("payment_state", "in", OPEN_PAYMENT_STATES),
                ("invoice_date_due", "<", limit),
                ("mirabilenet_service_id.state", "=", "activo")])
            for service in overdue.mapped("mirabilenet_service_id"):
                _t, created = service._request_transition(
                    "suspender", reason="Corte automático por mora",
                    key="corte-%d-%s" % (service.id, today.strftime("%Y%m%d")))
                total += int(created)
        return total
