"""La lista de precios de las sucursales funciona con la opción «Listas de precios» apagada.

Odoo, con esa opción apagada, avisa al abrir Ajustes que «se archivarán todas las listas de
precios activas» y, al guardar cualquier ajuste, las archiva. Archivar la de las sucursales
haría que la caja cobre los planes a precio completo (el mes lo cobra el contrato). Aquí:
- el aviso no cuenta la lista de las sucursales;
- al guardar Ajustes, la lista de las sucursales vuelve a quedar activa.

No se enciende la opción a propósito: con ella encendida, las ventas y el sitio tomarían esa
lista y los planes saldrían en cero también ahí."""
from odoo import _, api, models

from .pos_config import PRICELIST


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    @api.model
    def _mirabilenet_branch_pricelist(self):
        return self.env.ref(PRICELIST, raise_if_not_found=False)

    @api.onchange("group_product_pricelist")
    def _onchange_group_sale_pricelist(self):
        if self.group_product_pricelist:
            return None
        branch = self._mirabilenet_branch_pricelist()
        domain = [("active", "=", True)] + ([("id", "!=", branch.id)] if branch else [])
        if self.env["product.pricelist"].sudo().search_count(domain, limit=1):
            return {"warning": {"message": _(
                "You are deactivating the pricelist feature. "
                "Every active pricelist will be archived.")}}
        return None

    def set_values(self):
        branch = self._mirabilenet_branch_pricelist()
        was_active = bool(branch and branch.sudo().active)
        result = super().set_values()
        if was_active:
            branch = branch.sudo()
            branch.invalidate_recordset(["active"])
            if not branch.active:
                branch.action_unarchive()
            # La moneda de la lista no se toca, pero si quedó archivada por otro motivo
            # (otra moneda o compañía), la caja ya no la usa y no hace falta reactivarla.
        return result
