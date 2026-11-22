import calendar
from datetime import date

from odoo import fields, models


def day_in_month(year, month, day):
    """El día pedido dentro de ese mes; si el mes es más corto, su último día."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def next_day_of_month(start, day):
    """La primera fecha igual o posterior a `start` que cae en ese día del mes."""
    candidate = day_in_month(start.year, start.month, day)
    if candidate >= start:
        return candidate
    year, month = (start.year + 1, 1) if start.month == 12 else (start.year, start.month + 1)
    return day_in_month(year, month, day)


class ContractContract(models.Model):
    _inherit = "contract.contract"

    mirabilenet_service_id = fields.Many2one("mirabilenet.service", string="Servicio",
                                             readonly=True, index=True, ondelete="restrict")
    mirabilenet_region_id = fields.Many2one(
        related="mirabilenet_service_id.region_id", store=True, index=True, string="Región")

    def _prepare_invoice(self, date_invoice, journal=None):
        vals = super()._prepare_invoice(date_invoice, journal=journal)
        service = self.mirabilenet_service_id
        if service:
            region = service.region_id
            vals.update(mirabilenet_service_id=service.id, mirabilenet_region_id=region.id)
            if self.payment_term_id:
                pass
            elif service.payment_mode == "pospago":
                vals["invoice_date_due"] = fields.Date.to_date(date_invoice)
            elif region.dia_vencimiento:
                vals["invoice_date_due"] = next_day_of_month(
                    fields.Date.to_date(date_invoice), region.dia_vencimiento)
        return vals

    def _recurring_create_invoice(self, date_ref=False):
        """Las facturas de servicios se publican al emitirse: son el aviso de cobro."""
        moves = super()._recurring_create_invoice(date_ref=date_ref)
        ours = moves.filtered(lambda m: m.mirabilenet_service_id and m.invoice_line_ids
                              and m.state == "draft")
        ours.action_post()
        ours._mirabilenet_notify("aviso_emitido")
        return moves
