from odoo import fields, models, _
from odoo.exceptions import UserError

SERIAL_STATES = [
    ("en_almacen", "En almacén"),
    ("con_tecnico", "Asignado a técnico"),
    ("en_cliente", "Instalado en cliente"),
    ("en_reparacion", "En reparación"),
    ("baja", "De baja"),
]
#: Lo que solo fijan los movimientos.
TRACKED = {"mirabilenet_state", "mirabilenet_region_id", "mirabilenet_warehouse_id",
           "mirabilenet_technician_id", "mirabilenet_partner_id"}


class StockLot(models.Model):
    """La unidad física con número de serie: dónde está y quién la tiene."""
    _inherit = "stock.lot"

    mirabilenet_state = fields.Selection(
        SERIAL_STATES, string="Situación", readonly=True, index=True, copy=False,
        help="La fijan los movimientos de inventario.")
    mirabilenet_region_id = fields.Many2one("mirabilenet.region", string="Región",
                                            readonly=True, index=True, copy=False)
    mirabilenet_warehouse_id = fields.Many2one("stock.warehouse", string="Almacén",
                                               readonly=True, copy=False)
    mirabilenet_technician_id = fields.Many2one("res.users", string="Técnico", readonly=True,
                                                copy=False)
    mirabilenet_partner_id = fields.Many2one("res.partner", string="Cliente", readonly=True,
                                             index=True, copy=False)
    mirabilenet_mac = fields.Char(string="MAC")
    mirabilenet_supplier = fields.Char(string="Proveedor")
    mirabilenet_purchase_date = fields.Date(string="Fecha de compra")
    mirabilenet_warranty_until = fields.Date(string="Garantía hasta")
    mirabilenet_cost = fields.Float(string="Costo", digits="Product Price")

    def write(self, vals):
        if TRACKED & set(vals) and not self.env.su:
            raise UserError(_(
                "La situación de una serie cambia con un movimiento de inventario."))
        return super().write(vals)
