from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def reconcile(self):
        """Cuando un pago se aplica a una factura, se revisa si el cliente ya no debe."""
        invoices = self.sudo().mapped("move_id").filtered(
            lambda m: m.move_type == "out_invoice" and m.mirabilenet_region_id)
        was_open = invoices.filtered(lambda m: m._mirabilenet_is_open())
        result = super().reconcile()
        for invoice in was_open.filtered(lambda m: not m._mirabilenet_is_open()):
            invoice._mirabilenet_on_paid()
        for partner in invoices.mapped("partner_id"):
            partner._mirabilenet_evaluate_reactivation()
        return result
