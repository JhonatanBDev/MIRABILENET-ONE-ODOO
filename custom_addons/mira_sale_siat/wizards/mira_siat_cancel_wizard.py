from odoo import fields, models


class MiraSiatCancelWizard(models.TransientModel):
    _name = "mira.siat.cancel.wizard"
    _description = "Mira_Sale SIAT: anular documento fiscal"

    invoice_id = fields.Many2one("mira.siat.invoice", string="Documento fiscal",
                                 required=True, readonly=True)
    company_id = fields.Many2one(related="invoice_id.company_id")
    reason_id = fields.Many2one(
        "mira.siat.catalog.item", string="Motivo de anulación", required=True,
        domain="[('catalog_type', '=', 'motivo_anulacion'), "
               "('company_id', '=', company_id)]")

    def action_confirm(self):
        self.ensure_one()
        self.invoice_id._cancel(self.reason_id)
        return {"type": "ir.actions.act_window_close"}
