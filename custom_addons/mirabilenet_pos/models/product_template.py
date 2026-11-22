from odoo import api, models

PLAN_CATEGORY = "mirabilenet_pos.product_category_plans"


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("mirabilenet_is_plan"):
                self._mirabilenet_plan_defaults(vals)
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("mirabilenet_is_plan"):
            self._mirabilenet_plan_defaults(vals)
        return super().write(vals)

    @api.model
    def _mirabilenet_plan_defaults(self, vals):
        """Un plan se ofrece en las sucursales y va en la categoría que la lista de precios
        de las sucursales deja en cero: lo que se paga en caja es la instalación, el mes lo
        cobra el contrato."""
        category = self.env.ref(PLAN_CATEGORY, raise_if_not_found=False)
        if category:
            vals["categ_id"] = category.id
        vals.setdefault("available_in_pos", True)
