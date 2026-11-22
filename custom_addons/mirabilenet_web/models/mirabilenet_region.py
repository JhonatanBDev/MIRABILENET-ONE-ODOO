from odoo import api, models

from .mirabilenet_web_coverage import COVERAGE_STATES


class MirabilenetRegion(models.Model):
    _inherit = "mirabilenet.region"

    @api.model
    def _mirabilenet_coverage_localities(self):
        """Lo que el sitio publica también lo usa el asistente de ventas."""
        labels = dict(COVERAGE_STATES)
        localities = self.env["mirabilenet.web.coverage"].sudo().search(
            [("region_id.active", "=", True)])
        return super()._mirabilenet_coverage_localities() + [
            (l.region_id, l.name, labels[l.state], l.detail or "") for l in localities]
