import logging

from odoo import api, models

from odoo.addons.mirabilenet_whatsapp.whatsapp import content, phones

_logger = logging.getLogger(__name__)


class MirabilenetConversation(models.Model):
    """Si quien escribe es del personal, su mensaje es trabajo, no un cliente ni un prospecto:
    no abre conversación ni pasa por el bot de ventas."""
    _inherit = "mirabilenet.conversation"

    @api.model
    def _process_meta_incoming(self, incoming, phone_number_id=""):
        try:
            number = phones.normalize_number(str(incoming.get("from") or ""))
        except phones.NotSendable:
            number = ""
        staff = self.env["res.users"]._mirabilenet_staff_by_number(number)
        if not staff:
            return super()._process_meta_incoming(incoming, phone_number_id)
        kind, text, data = content.normalize_meta_incoming(incoming)
        result = self.env["mirabilenet.staff.notice"]._handle_incoming(
            staff, kind, text, data, str(incoming.get("id") or "")[:120])
        _logger.info("Mensaje del personal (%s): %s", staff.login, result)
        return "personal"
