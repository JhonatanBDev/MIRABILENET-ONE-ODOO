from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    mira_siat_payment_method_id = fields.Many2one(
        "mira.siat.catalog.item", string="Método de pago SIAT",
        domain="[('catalog_type', '=', 'tipo_metodo_pago'), ('company_id', '=', company_id)]",
        help="Método del catálogo del SIN que representan los cobros de este diario. "
             "Con esto la factura deduce sola su método de pago.")
    mira_siat_sector = fields.Selection(
        [("1", "Factura de Compra y Venta"), ("22", "Factura de Telecomunicaciones")],
        string="Documento sector SIAT",
        help="Documento sector de las facturas de este diario de ventas. Vacío = el "
             "de la empresa.")
