import logging

from odoo import api, fields, models, modules, _

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    mirabilenet_fiscal_pending = fields.Boolean(
        string="Factura fiscal pendiente", copy=False, index=True, readonly=True,
        help="El pago ya está registrado; la emisión ante el SIN falló y se reintenta sola.")
    mirabilenet_fiscal_error = fields.Char(string="Último error fiscal", copy=False,
                                           readonly=True)
    mirabilenet_fiscal_user_id = fields.Many2one(
        "res.users", string="Pago registrado por", copy=False, readonly=True,
        help="Quien registró el pago que disparó la factura fiscal.")

    def _mirabilenet_on_paid(self):
        """La factura quedó pagada: se emite la fiscal. Un fallo del SIN nunca deshace el
        pago; queda anotado y se reintenta."""
        result = super()._mirabilenet_on_paid()
        if self.env.su and self.env.context.get("mirabilenet_migration"):
            return result  # pagos históricos: no se emiten facturas fiscales con fecha vieja
        for move in self.sudo().filtered(lambda m: m.company_id.mirabilenet_invoice_on_payment):
            move.mirabilenet_fiscal_user_id = self.env.user
            move._mirabilenet_fiscal_try()
        return result

    def _mirabilenet_fiscal_emit(self):
        self.ensure_one()
        invoice = self.env["mira.siat.invoice"].sudo()._issue(
            self, self._mira_siat_idempotency_key())
        if invoice.state == "rejected":
            self.write({"mirabilenet_fiscal_pending": True, "mirabilenet_fiscal_error": _(
                "El SIN rechazó la factura. Corrija los datos y reintente.")})
        else:
            self.write({"mirabilenet_fiscal_pending": False, "mirabilenet_fiscal_error": False})

    def _mirabilenet_fiscal_try(self):
        """Un intento, aislado: su fallo queda anotado y no afecta a nada más."""
        self.ensure_one()
        move = self.sudo()
        try:
            if modules.module.current_test:
                with self.env.cr.savepoint():
                    move._mirabilenet_fiscal_emit()
            else:
                # El módulo SIAT confirma la transacción a mitad de la emisión: aquí no
                # puede usarse un savepoint.
                move._mirabilenet_fiscal_emit()
        except Exception as exc:  # pylint: disable=broad-except
            _logger.exception("Factura fiscal de %s no emitida", move.name)
            move.write({"mirabilenet_fiscal_pending": True,
                        "mirabilenet_fiscal_error": str(exc)[:250] or exc.__class__.__name__})
            self.env["mirabilenet.audit.log"]._log(
                "modificar", "La factura fiscal de %s no se pudo emitir" % move.name,
                record=move, region=move.mirabilenet_region_id)
        return not move.mirabilenet_fiscal_pending

    @api.model
    def _cron_emit_fiscal_invoices(self, limit=50):
        """Reintenta las facturas fiscales que quedaron pendientes."""
        pending = self.sudo().search(
            [("mirabilenet_fiscal_pending", "=", True), ("state", "=", "posted")],
            order="id", limit=limit)
        return sum(1 for move in pending if move._mirabilenet_fiscal_try())
