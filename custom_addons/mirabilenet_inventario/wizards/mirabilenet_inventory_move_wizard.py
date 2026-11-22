from odoo import api, fields, models

from ..models.stock_move import KINDS


class MirabilenetInventoryMoveWizard(models.TransientModel):
    """Registrar un movimiento de inventario. Las reglas están en stock.move."""
    _name = "mirabilenet.inventory.move.wizard"
    _description = "MIRABILENET: movimiento de inventario"

    kind = fields.Selection(KINDS, string="Tipo", required=True, default="compra")
    product_id = fields.Many2one(
        "product.product", string="Artículo", required=True,
        domain="[('is_storable', '=', True)]")
    tracking = fields.Selection(related="product_id.tracking")
    lot_id = fields.Many2one("stock.lot", string="Serie",
                             domain="[('product_id', '=', product_id)]")
    lot_name = fields.Char(string="Número de serie nuevo")
    quantity = fields.Float(string="Cantidad", default=1.0)
    source_id = fields.Many2one("stock.warehouse", string="Almacén de origen")
    dest_id = fields.Many2one("stock.warehouse", string="Almacén de destino")
    technician_id = fields.Many2one("res.users", string="Técnico")
    partner_id = fields.Many2one("res.partner", string="Cliente",
                                 domain="[('mirabilenet_is_customer', '=', True)]")
    document = fields.Char(string="Documento")
    reason = fields.Char(string="Motivo")

    @api.onchange("product_id")
    def _onchange_product_id(self):
        self.lot_id = False

    @api.onchange("lot_id")
    def _onchange_lot_id(self):
        if self.lot_id.mirabilenet_warehouse_id and not self.source_id:
            self.source_id = self.lot_id.mirabilenet_warehouse_id

    def action_confirm(self):
        self.ensure_one()
        move = self.env["stock.move"]._mirabilenet_move(
            self.kind, self.product_id, quantity=self.quantity, lot=self.lot_id or None,
            lot_name=self.lot_name, source=self.source_id or None, dest=self.dest_id or None,
            technician=self.technician_id or None, partner=self.partner_id or None,
            document=self.document or "", reason=self.reason or "")
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"type": "success", "message": move.reference or "Movimiento registrado",
                       "next": {"type": "ir.actions.act_window_close"}},
        }
