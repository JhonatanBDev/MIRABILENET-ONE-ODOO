"""Cobros sobre lo nativo: el servicio se cobra con un contrato recurrente (OCA `contract`) que
emite facturas de Odoo. Aquí solo va lo que une esas piezas con la red y con la región."""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MirabilenetService(models.Model):
    _inherit = "mirabilenet.service"

    contract_id = fields.Many2one("contract.contract", string="Contrato de cobro", readonly=True,
                                  copy=False, ondelete="restrict")
    invoice_ids = fields.One2many("account.move", "mirabilenet_service_id", string="Facturas")
    amount_due = fields.Monetary(string="Saldo pendiente", compute="_compute_amount_due")

    @api.depends("invoice_ids.amount_residual", "invoice_ids.state")
    def _compute_amount_due(self):
        for service in self:
            service.amount_due = sum(service.sudo().invoice_ids.filtered(
                lambda m: m.state == "posted" and m.move_type == "out_invoice"
            ).mapped("amount_residual"))

    def _mirabilenet_ensure_contract(self, activation=None):
        """Crea el contrato de cobro del servicio la primera vez que se activa."""
        self.ensure_one()
        service = self.sudo()
        if service.contract_id:
            return service.contract_id
        product = service.plan_id.product_variant_id
        if not product:
            raise UserError(_("El plan del servicio %s no tiene producto.", service.name))
        start = activation or service.date_start or fields.Date.context_today(self)
        if not service.date_start:
            service.date_start = start
        line = {"product_id": product.id, "name": service.plan_id.name, "quantity": 1,
                "uom_id": product.uom_id.id, "price_unit": service.monthly_price,
                "recurring_interval": 1, "date_start": start}
        if service.payment_mode == "pospago":
            # Meses enteros desde el día del alta: el alta del 3 paga el 3 de cada mes.
            line.update(recurring_rule_type="monthly", qty_type="fixed",
                        recurring_invoicing_type="post-paid")
        else:
            # Meses calendario avisados el día de emisión prepago de la región; el primero
            # se cobra solo por los días desde el alta.
            formula = self.env.ref(
                "contract_variable_qty_prorated.contract_variable_qty_prorated")
            line.update(recurring_rule_type="monthlylastday", qty_type="variable",
                        qty_formula_id=formula.id, recurring_invoicing_type="pre-paid")
        contract = self.env["contract.contract"].sudo().create({
            "name": service.name, "partner_id": service.partner_id.id, "contract_type": "sale",
            "date_start": start,
            "company_id": service.region_id.company_id.id or self.env.company.id,
            "line_recurrence": True, "mirabilenet_service_id": service.id,
            "contract_line_ids": [(0, 0, line)],
        })
        service.contract_id = contract
        self.env["mirabilenet.audit.log"]._log(
            "crear", "Contrato de cobro de %s desde el %s" % (service.name, start),
            record=service, region=service.region_id, payload={"contrato": contract.id})
        return contract

    def _mirabilenet_on_activated(self, transition):
        result = super()._mirabilenet_on_activated(transition)
        self._mirabilenet_ensure_contract()
        return result

    def _apply_confirmed_state(self, action):
        result = super()._apply_confirmed_state(action)
        if action == "baja":
            # Dado de baja: el contrato deja de emitir. Si el cobro aún no había empezado,
            # se archiva; si ya corría, su línea termina en la fecha de baja.
            end = self.date_end or fields.Date.context_today(self)
            contract = self.sudo().contract_id
            for line in contract.contract_line_ids:
                if line.date_start > end:
                    contract.active = False
                elif not line.date_end or line.date_end > end:
                    line.date_end = end
        return result

    def write(self, vals):
        result = super().write(vals)
        if "monthly_price" in vals:
            # El precio del servicio manda: el contrato lo sigue desde la próxima emisión.
            for service in self.sudo().filtered("contract_id"):
                service.contract_id.contract_line_ids.write({"price_unit": service.monthly_price})
        return result
