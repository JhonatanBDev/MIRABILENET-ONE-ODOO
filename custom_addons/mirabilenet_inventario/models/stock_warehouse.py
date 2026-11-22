from odoo import fields, models


class StockWarehouse(models.Model):
    """El almacén de Odoo, colgado de una sucursal y, por ella, de una región."""
    _name = "stock.warehouse"
    _inherit = ["stock.warehouse", "mirabilenet.region.scoped"]
    _region_path = ("mirabilenet_branch_id",)

    mirabilenet_branch_id = fields.Many2one(
        "mirabilenet.branch", string="Sucursal", ondelete="restrict", index=True)
    mirabilenet_region_id = fields.Many2one(
        related="mirabilenet_branch_id.region_id", store=True, index=True, string="Región")
    mirabilenet_responsible_id = fields.Many2one("res.users", string="Responsable",
                                                 ondelete="set null")

    def _mirabilenet_sublocation(self, name):
        """Ubicación interna del almacén para equipos fuera del depósito: con técnicos o
        en reparación. Se crea la primera vez que hace falta."""
        self.ensure_one()
        warehouse = self.sudo()
        Location = self.env["stock.location"].sudo()
        location = Location.search(
            [("location_id", "=", warehouse.view_location_id.id), ("name", "=", name),
             ("usage", "=", "internal")], limit=1)
        return location or Location.create({
            "name": name, "usage": "internal", "location_id": warehouse.view_location_id.id,
            "company_id": warehouse.company_id.id})
