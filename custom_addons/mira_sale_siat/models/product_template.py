from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _mira_siat_activity_domain(self):
        company = self.env.company
        domain = [("catalog_type", "=", "actividades"), ("company_id", "=", company.id)]
        if company.mira_siat_activity_ids:
            domain.append(("id", "in", company.mira_siat_activity_ids.ids))
        return domain

    mira_siat_activity_id = fields.Many2one(
        "mira.siat.catalog.item", string="Actividad económica (SIAT)",
        company_dependent=True, domain=lambda self: self._mira_siat_activity_domain())
    mira_siat_activity_code = fields.Char(compute="_compute_mira_siat_activity_code")
    mira_siat_company_id = fields.Many2one(
        "res.company", compute="_compute_mira_siat_activity_code")
    mira_siat_product_id = fields.Many2one(
        "mira.siat.catalog.item", string="Producto/servicio SIN",
        company_dependent=True,
        domain=lambda self: [("catalog_type", "=", "productos_servicios"),
                             ("company_id", "=", self.env.company.id)])
    mira_siat_unit_id = fields.Many2one(
        "mira.siat.catalog.item", string="Unidad de medida SIN",
        company_dependent=True,
        domain=lambda self: [("catalog_type", "=", "unidad_medida"),
                             ("company_id", "=", self.env.company.id)],
        help="Si se deja vacía se usa la unidad por defecto de la empresa.")
    mira_siat_is_discount = fields.Boolean(
        string="Es un descuento",
        help="Producto usado para líneas de descuento: no se envía como ítem y no "
             "necesita homologación.")
    mira_siat_homologated = fields.Boolean(
        string="Homologado SIAT", compute="_compute_mira_siat_homologated",
        search="_search_mira_siat_homologated")

    @api.depends("mira_siat_activity_id")
    @api.depends_context("company")
    def _compute_mira_siat_activity_code(self):
        for template in self:
            template.mira_siat_activity_code = template.mira_siat_activity_id.code
            template.mira_siat_company_id = self.env.company

    @api.depends("mira_siat_activity_id", "mira_siat_product_id", "mira_siat_unit_id",
                 "mira_siat_is_discount")
    @api.depends_context("company")
    def _compute_mira_siat_homologated(self):
        default_unit = self.env.company.mira_siat_default_unit_id
        for template in self:
            template.mira_siat_homologated = bool(
                template.mira_siat_is_discount or (
                    template.mira_siat_activity_id and template.mira_siat_product_id
                    and (template.mira_siat_unit_id or default_unit)))

    def _search_mira_siat_homologated(self, operator, value):
        truthy = any(value) if isinstance(value, (list, tuple, set)) else bool(value)
        positive = truthy if operator in ("=", "in") else not truthy
        mapped = [("mira_siat_activity_id", "!=", False), ("mira_siat_product_id", "!=", False)]
        if not self.env.company.mira_siat_default_unit_id:
            mapped.append(("mira_siat_unit_id", "!=", False))
        ok_ids = self.with_context(active_test=False).search(
            ["|", ("mira_siat_is_discount", "=", True)]
            + ["&"] * (len(mapped) - 1) + mapped).ids
        return [("id", "in" if positive else "not in", ok_ids)]

    @api.onchange("mira_siat_activity_id")
    def _onchange_mira_siat_activity_id(self):
        product = self.mira_siat_product_id
        if product and product.activity_code != self.mira_siat_activity_id.code:
            self.mira_siat_product_id = False

    def _mira_siat_mapping(self, company):
        """(actividad, producto SIN, unidad) de la empresa, o None si falta algo."""
        self.ensure_one()
        template = self.with_company(company)
        unit = template.mira_siat_unit_id or company.mira_siat_default_unit_id
        if not (template.mira_siat_activity_id and template.mira_siat_product_id and unit):
            return None
        return template.mira_siat_activity_id, template.mira_siat_product_id, unit
