from odoo import api, fields, models

OPEN_PAYMENT_STATES = ("not_paid", "partial")


class AccountMove(models.Model):
    _inherit = "account.move"

    mirabilenet_service_id = fields.Many2one("mirabilenet.service", string="Servicio",
                                             index=True, ondelete="restrict", copy=False)
    mirabilenet_region_id = fields.Many2one("mirabilenet.region", string="Región", index=True,
                                            ondelete="restrict")

    @api.model_create_multi
    def create(self, vals_list):
        """Una factura hecha a mano para un cliente de MIRABILENET toma su región."""
        for vals in vals_list:
            if not vals.get("mirabilenet_region_id") and vals.get("partner_id"):
                partner = self.env["res.partner"].sudo().browse(vals["partner_id"])
                vals["mirabilenet_region_id"] = partner.mirabilenet_region_id.id
        return super().create(vals_list)

    # -- Lo que el resto de MIRABILENET le pide a una factura ----------------------
    @api.model
    def _mirabilenet_today(self):
        return fields.Date.context_today(self)

    @api.model
    def _mirabilenet_open_domain(self):
        """Facturas a clientes publicadas y con saldo: lo que antes era un aviso pendiente."""
        return [("move_type", "=", "out_invoice"), ("state", "=", "posted"),
                ("payment_state", "in", OPEN_PAYMENT_STATES)]

    def _mirabilenet_is_open(self):
        self.ensure_one()
        return (self.move_type == "out_invoice" and self.state == "posted"
                and self.payment_state in OPEN_PAYMENT_STATES)

    def _mirabilenet_charge_state(self):
        """El estado de cobro con las palabras que usan los avisos y los flujos de n8n."""
        self.ensure_one()
        if self.state == "draft":
            return "borrador"
        if self.state == "cancel":
            return "anulado"
        if self.payment_state not in OPEN_PAYMENT_STATES:
            return "pagado"
        if self.invoice_date_due and self.invoice_date_due < self._mirabilenet_today():
            return "vencido"
        return "pago_parcial" if self.payment_state == "partial" else "emitido"

    def _mirabilenet_concept(self):
        self.ensure_one()
        line = self.invoice_line_ids.filtered(lambda l: l.display_type == "product")[:1]
        return (line.name or self.invoice_origin or self.name or "").splitlines()[0] \
            if (line.name or self.invoice_origin or self.name) else ""

    def _mirabilenet_notify(self, event):
        """Punto de enganche para la mensajería. Aquí no avisa nadie."""
        return None

    def _mirabilenet_on_paid(self):
        """Punto de enganche para cuando la factura queda pagada (la factura fiscal)."""
        return None

    def _mirabilenet_register_payment(self, amount=None, memo=""):
        """Registra un pago de Odoo contra esta factura. El autor es el usuario real."""
        self.ensure_one()
        move = self.sudo()
        values = {"amount": amount or move.amount_residual}
        if memo:
            values["communication"] = memo
        wizard = self.env["account.payment.register"].sudo().with_context(
            active_model="account.move", active_ids=move.ids).create(values)
        return wizard._create_payments()
