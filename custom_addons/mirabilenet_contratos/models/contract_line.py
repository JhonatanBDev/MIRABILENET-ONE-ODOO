from odoo import api, models


class ContractLine(models.Model):
    _inherit = "contract.line"

    @api.depends("recurring_invoicing_type", "recurring_rule_type",
                 "contract_id.mirabilenet_service_id.region_id.dia_emision_prepago")
    def _compute_recurring_invoicing_offset(self):
        """El prepago de un servicio se avisa el día de emisión prepago de su región."""
        result = super()._compute_recurring_invoicing_offset()
        for line in self:
            region = line.contract_id.mirabilenet_service_id.region_id
            if (region and line.recurring_invoicing_type == "pre-paid"
                    and line.recurring_rule_type == "monthlylastday"):
                line.recurring_invoicing_offset = max((region.dia_emision_prepago or 1) - 1, 0)
        return result
