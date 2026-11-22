from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    mirabilenet_invoice_on_payment = fields.Boolean(
        string="Emitir la factura fiscal al registrar el pago",
        help="Apagado, la factura fiscal se emite a mano con el botón SIAT de la factura.")
