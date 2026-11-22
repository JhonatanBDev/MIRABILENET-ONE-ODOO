"""Las sucursales cobran y reciben solicitudes de servicio con el Punto de venta de Odoo.
Aquí solo va lo que une un punto de venta con su sucursal y una venta con la red."""
from odoo import api, fields, models

PRICELIST = "mirabilenet_pos.pricelist_branch"


class PosConfig(models.Model):
    _inherit = "pos.config"

    mirabilenet_branch_id = fields.Many2one("mirabilenet.branch", string="Sucursal",
                                            ondelete="restrict", index=True)
    mirabilenet_region_id = fields.Many2one(related="mirabilenet_branch_id.region_id",
                                            store=True, index=True, string="Región")

    @api.model_create_multi
    def create(self, vals_list):
        configs = super().create(vals_list)
        configs.filtered("mirabilenet_branch_id")._mirabilenet_use_branch_pricelist()
        return configs

    def write(self, vals):
        result = super().write(vals)
        if vals.get("mirabilenet_branch_id"):
            self._mirabilenet_use_branch_pricelist()
        return result

    def _mirabilenet_use_branch_pricelist(self):
        pricelist = self.env.ref(PRICELIST).sudo()
        for config in self.sudo():
            if pricelist.currency_id != config.currency_id or (
                    pricelist.company_id and pricelist.company_id != config.company_id):
                continue  # una sucursal en otra moneda o empresa necesita su propia lista
            # Una sola lista: la de la sucursal. Con «varias listas» apagado, Odoo usa solo la
            # predeterminada y no hace falta tocar las disponibles.
            config.write({"use_pricelist": False, "pricelist_id": pricelist.id})
