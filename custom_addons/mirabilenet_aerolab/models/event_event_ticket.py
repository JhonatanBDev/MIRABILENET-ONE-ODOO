from odoo import api, models


class EventEventTicket(models.Model):
    _inherit = "event.event.ticket"

    @api.constrains("price")
    def _check_mirabilenet_price(self):
        self.mapped("event_id")._check_mirabilenet_publication()

    def unlink(self):
        events = self.mapped("event_id")
        result = super().unlink()
        events.exists()._check_mirabilenet_publication()
        return result
