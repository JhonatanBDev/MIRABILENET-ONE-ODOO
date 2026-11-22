from odoo import fields, models

from .account_move import OPEN_PAYMENT_STATES


class ResPartner(models.Model):
    _inherit = "res.partner"

    mirabilenet_balance = fields.Monetary(
        string="Saldo pendiente", compute="_compute_mirabilenet_balance",
        currency_field="currency_id",
        help="Sale de las facturas publicadas y sus saldos, nunca del estado del servicio.")

    def _mirabilenet_open_invoices(self):
        return self.env["account.move"].sudo().search([
            ("partner_id", "in", self.ids), ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"), ("payment_state", "in", OPEN_PAYMENT_STATES)])

    def _compute_mirabilenet_balance(self):
        invoices = self._mirabilenet_open_invoices()
        for partner in self:
            partner.mirabilenet_balance = sum(invoices.filtered(
                lambda m: m.partner_id == partner).mapped("amount_residual"))

    def _mirabilenet_evaluate_reactivation(self):
        """Tras un pago: si ya no debe nada, pide reactivar sus servicios."""
        self.ensure_one()
        partner = self.sudo()
        Transition = self.env["mirabilenet.service.transition"]
        if self.env.su and self.env.context.get("mirabilenet_migration"):
            return Transition  # pagos históricos: la red ya está como estaba
        if partner._mirabilenet_open_invoices():
            return Transition
        stamp = fields.Datetime.now().strftime("%Y%m%d%H%M")
        services = self.env["mirabilenet.service"].sudo().search(
            [("partner_id", "=", partner.id), ("state", "in", ("suspendido", "moroso"))])
        transitions = Transition
        for service in services.filtered(lambda s: s.region_id.reactivacion_automatica):
            transition, _created = service._request_transition(
                "activar", reason="Reactivación por pago", key="react-%d-%s" % (service.id, stamp))
            transitions |= transition
        return transitions
