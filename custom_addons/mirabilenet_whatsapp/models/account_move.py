import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class MirabilenetCharge(models.Model):
    _inherit = "account.move"

    whatsapp_message_ids = fields.One2many("mirabilenet.whatsapp.message", "charge_id",
                                           string="Mensajes de WhatsApp")

    def _mirabilenet_notify(self, event):
        """Los cobros avisan aquí. Un fallo de la mensajería nunca frena la cobranza."""
        result = super()._mirabilenet_notify(event)
        Message = self.env["mirabilenet.whatsapp.message"]
        for charge in self:
            try:
                with self.env.cr.savepoint():
                    if Message._enqueue(event, charge=charge):
                        Message._trigger_dispatch()
            except Exception:
                _logger.exception("No se pudo encolar el WhatsApp de %s", charge.name)
        return result
