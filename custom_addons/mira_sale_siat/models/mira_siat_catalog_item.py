from odoo import api, fields, models


class MiraSiatCatalogItem(models.Model):
    _name = "mira.siat.catalog.item"
    _description = "Mira_Sale SIAT: elemento de catálogo"
    _order = "catalog_type, code"
    _rec_names_search = ["code", "name"]

    catalog_id = fields.Many2one("mira.siat.catalog", required=True, ondelete="cascade",
                                 index=True)
    company_id = fields.Many2one(related="catalog_id.company_id", store=True, index=True)
    catalog_type = fields.Selection(related="catalog_id.catalog_type", store=True, index=True)
    code = fields.Char(string="Código", required=True, index=True)
    name = fields.Char(string="Descripción", required=True)
    activity_code = fields.Char(string="Actividad económica")
    extra = fields.Char(string="Dato adicional")
    active = fields.Boolean(default=True)
    # Métodos de pago
    components = fields.Char(
        string="Medios que lo componen", readonly=True,
        help="Medios simples del método, separados por «|». Vacío si el nombre "
             "del catálogo no se pudo interpretar.")
    includes_card = fields.Boolean(string="Incluye tarjeta", readonly=True)
    includes_gift_card = fields.Boolean(string="Incluye gift card", readonly=True)
    # Monedas
    currency_id = fields.Many2one(
        "res.currency", string="Moneda de Odoo",
        help="Moneda de Odoo que corresponde a este código de moneda del SIN.")

    _currency_uniq = models.Constraint(
        "unique(catalog_id, currency_id)",
        "Esa moneda ya está vinculada a otro código del SIN.")

    @api.depends("code", "name", "catalog_type")
    def _compute_display_name(self):
        for item in self:
            if item.catalog_type == "leyendas":
                item.display_name = item.name
            else:
                item.display_name = "[%s] %s" % (item.code, item.name)
