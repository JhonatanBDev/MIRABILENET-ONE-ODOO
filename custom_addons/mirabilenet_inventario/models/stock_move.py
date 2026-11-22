from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_compare

STOCK_USER = "mirabilenet_inventario.group_mirabilenet_stock_user"
KINDS = [
    ("compra", "Compra / entrada"),
    ("salida_tecnico", "Salida a técnico"),
    ("transferencia", "Transferencia entre almacenes"),
    ("asignacion_cliente", "Asignación a cliente"),
    ("devolucion", "Devolución"),
    ("reparacion", "Envío a reparación"),
    ("baja", "Baja"),
    ("ajuste", "Ajuste por conteo"),
    ("consumo", "Consumo de material"),
]
#: Situación en que queda la serie tras cada movimiento (None = no cambia).
SERIAL_STATE_AFTER = {
    "compra": "en_almacen", "salida_tecnico": "con_tecnico", "transferencia": None,
    "asignacion_cliente": "en_cliente", "devolucion": "en_almacen",
    "reparacion": "en_reparacion", "baja": "baja",
}
TECH_LOCATION = "Con técnicos"
REPAIR_LOCATION = "En reparación"


class StockMove(models.Model):
    """El movimiento de Odoo, con el tipo y los datos que pide la operación de MIRABILENET.

    Un movimiento hecho no se borra ni se edita: se revierte con otro movimiento.
    """
    _inherit = "stock.move"

    mirabilenet_kind = fields.Selection(KINDS, string="Tipo de movimiento", readonly=True,
                                        index=True)
    mirabilenet_region_id = fields.Many2one("mirabilenet.region", string="Región",
                                            readonly=True, index=True)
    mirabilenet_lot_id = fields.Many2one("stock.lot", string="Serie", readonly=True,
                                         index=True)
    mirabilenet_source_id = fields.Many2one("stock.warehouse", string="Almacén de origen",
                                            readonly=True)
    mirabilenet_dest_id = fields.Many2one("stock.warehouse", string="Almacén de destino",
                                          readonly=True)
    mirabilenet_technician_id = fields.Many2one("res.users", string="Técnico", readonly=True)
    mirabilenet_partner_id = fields.Many2one("res.partner", string="Cliente", readonly=True)
    mirabilenet_document = fields.Char(string="Documento", readonly=True)
    mirabilenet_reason = fields.Char(string="Motivo", readonly=True)
    mirabilenet_user_id = fields.Many2one("res.users", string="Registrado por", readonly=True)

    @api.model
    def _mirabilenet_virtual(self, name):
        return self.env.ref("mirabilenet_inventario.location_%s" % name).sudo()

    @api.model
    def _mirabilenet_available(self, product, location, lot=None):
        return self.env["stock.quant"].sudo()._get_available_quantity(
            product, location, lot_id=lot, strict=True, allow_negative=True)

    @api.model
    def _mirabilenet_serial_location(self, lot):
        """Dónde está hoy la unidad, según las existencias reales."""
        quant = self.env["stock.quant"].sudo().search(
            [("lot_id", "=", lot.id), ("quantity", ">", 0),
             ("location_id.usage", "in", ("internal", "customer"))], limit=1)
        return quant.location_id

    @api.model
    def _mirabilenet_move(self, kind, product, quantity=1, lot=None, lot_name=None,
                          source=None, dest=None, technician=None, partner=None,
                          document="", reason=""):
        """Registra un movimiento y deja al día existencias y situación de la serie.

        `source` y `dest` son almacenes. Devuelve el movimiento hecho.
        """
        if not self.env.su and not self.env.user.has_group(STOCK_USER):
            raise AccessError(_("Su rol no registra movimientos de inventario."))
        if kind not in dict(KINDS):
            raise UserError(_("Tipo de movimiento desconocido."))
        Warehouse = self.env["stock.warehouse"]
        # El acceso se comprueba como quien opera, venga cada registro de donde venga.
        source = source.with_env(self.env) if source else Warehouse
        dest = dest.with_env(self.env) if dest else Warehouse
        (source | dest).check_access("read")
        product = product.sudo()
        if product._name == "product.template":
            product = product.product_variant_id
        if not product.is_storable:
            raise UserError(_("%s no lleva control de existencias.", product.display_name))
        serialized = product.tracking == "serial"
        lot = lot.sudo() if lot else self.env["stock.lot"].sudo()
        if lot:
            lot.with_env(self.env).check_access("read")
        current = self.env["stock.location"].sudo()

        if serialized:
            quantity = 1
            if kind in ("ajuste", "consumo"):
                raise UserError(_(
                    "Un artículo con número de serie no se ajusta ni se consume: se da de "
                    "baja o se devuelve."))
            if kind == "compra":
                if lot:
                    raise UserError(_("Esa serie ya existe: una compra crea una serie nueva."))
                if not (lot_name or "").strip():
                    raise UserError(_(
                        "%s es serializado: falta el número de serie.", product.display_name))
            else:
                if not lot or lot.product_id != product:
                    raise UserError(_(
                        "%s es serializado: indique su número de serie.", product.display_name))
                current = self._mirabilenet_serial_location(lot)
                if not current:
                    raise UserError(_(
                        "La serie %s no está en ningún almacén, técnico ni cliente.", lot.name))
                source = source or lot.mirabilenet_warehouse_id.with_env(self.env)
        else:
            lot = self.env["stock.lot"].sudo()
            if quantity <= 0:
                raise UserError(_("La cantidad debe ser mayor a cero."))
            if kind not in ("compra", "transferencia", "ajuste", "consumo"):
                raise UserError(_(
                    "Ese movimiento es para artículos con número de serie. El material a "
                    "granel se compra, se transfiere, se consume o se ajusta."))

        customers = self.env.ref("stock.stock_location_customers").sudo()
        suppliers = self.env.ref("stock.stock_location_suppliers").sudo()

        def need(warehouse, label):
            if not warehouse:
                raise UserError(_("Indique el almacén de %s.", label))
            return warehouse.sudo()

        if kind == "compra":
            src_loc, dst_loc = suppliers, need(dest, _("destino")).lot_stock_id
        elif kind == "salida_tecnico":
            if not technician:
                raise UserError(_("Indique el técnico que recibe el equipo."))
            warehouse = need(source, _("origen"))
            src_loc, dst_loc = current, warehouse._mirabilenet_sublocation(TECH_LOCATION)
            if current != warehouse.lot_stock_id:
                raise UserError(_("La serie %s no está en ese almacén.", lot.name))
        elif kind == "transferencia":
            src_loc = need(source, _("origen")).lot_stock_id
            dst_loc = need(dest, _("destino")).lot_stock_id
            if source == dest:
                raise UserError(_("El origen y el destino son el mismo almacén."))
            if serialized and current != src_loc:
                raise UserError(_("La serie %s no está en el almacén de origen.", lot.name))
        elif kind == "asignacion_cliente":
            if not partner or not partner.sudo().mirabilenet_is_customer:
                raise UserError(_("Indique el cliente que recibe el equipo."))
            partner.with_env(self.env).check_access("read")
            if current.usage != "internal":
                raise UserError(_("La serie %s ya está instalada en un cliente.", lot.name))
            src_loc, dst_loc = current, customers
        elif kind == "devolucion":
            src_loc, dst_loc = current, need(dest, _("destino")).lot_stock_id
            if current == dst_loc:
                raise UserError(_("La serie %s ya está en ese almacén.", lot.name))
        elif kind == "reparacion":
            warehouse = need(source, _("origen"))
            src_loc, dst_loc = current, warehouse._mirabilenet_sublocation(REPAIR_LOCATION)
        elif kind == "baja":
            src_loc, dst_loc = current, self._mirabilenet_virtual("baja")
        elif kind == "consumo":
            src_loc = need(source, _("origen")).lot_stock_id
            dst_loc = self._mirabilenet_virtual("consumo")
        else:  # ajuste: entra por el destino o sale por el origen
            if bool(source) == bool(dest):
                raise UserError(_(
                    "Un ajuste lleva solo un almacén: destino si sobra, origen si falta."))
            virtual = self._mirabilenet_virtual("ajuste")
            src_loc = source.sudo().lot_stock_id if source else virtual
            dst_loc = dest.sudo().lot_stock_id if dest else virtual

        region = (dest or source).sudo().mirabilenet_region_id or lot.mirabilenet_region_id
        if not region:
            raise UserError(_(
                "El movimiento necesita una región: el almacén debe tener sucursal."))
        if partner and partner.sudo().mirabilenet_region_id != region:
            raise UserError(_("El cliente es de otra región."))
        if lot and lot.mirabilenet_state == "baja":
            raise UserError(_("La serie %s está dada de baja.", lot.name))

        if not serialized and src_loc.usage == "internal" and kind != "ajuste":
            available = self._mirabilenet_available(product, src_loc)
            if float_compare(available, quantity,
                             precision_rounding=product.uom_id.rounding) < 0:
                raise UserError(_(
                    "Existencia insuficiente de %(product)s en %(warehouse)s: hay %(qty)s.",
                    product=product.display_name, warehouse=source.sudo().code, qty=available))

        if kind == "compra" and serialized:
            Lot = self.env["stock.lot"].sudo()
            if Lot.search_count([("name", "=", lot_name.strip()),
                                 ("product_id", "=", product.id)]):
                raise UserError(_("La serie %s ya existe.", lot_name.strip()))
            lot = Lot.create({"name": lot_name.strip(), "product_id": product.id,
                              "company_id": dest.sudo().company_id.id})

        move = self.sudo().create({
            "product_id": product.id, "product_uom": product.uom_id.id,
            "product_uom_qty": quantity,
            "location_id": src_loc.id, "location_dest_id": dst_loc.id,
            "company_id": (dest or source).sudo().company_id.id or self.env.company.id,
            "origin": document or False,
            "mirabilenet_kind": kind, "mirabilenet_region_id": region.id,
            "mirabilenet_lot_id": lot.id,
            "mirabilenet_source_id": source.id, "mirabilenet_dest_id": dest.id,
            "mirabilenet_technician_id": technician.id if technician else False,
            "mirabilenet_partner_id": partner.id if partner else False,
            "mirabilenet_document": document or False, "mirabilenet_reason": reason or False,
            "mirabilenet_user_id": self.env.user.id,
        })
        move._action_confirm()
        if lot:
            move.lot_ids = lot
        move.quantity = quantity
        move.picked = True
        move._action_done()
        if move.state != "done":
            raise UserError(_("El movimiento no se pudo completar."))

        if lot:
            new_state = SERIAL_STATE_AFTER[kind]
            vals = {"mirabilenet_region_id": region.id}
            if new_state:
                vals["mirabilenet_state"] = new_state
            if kind in ("compra", "devolucion", "transferencia"):
                vals.update(mirabilenet_warehouse_id=dest.id, mirabilenet_technician_id=False,
                            mirabilenet_partner_id=False)
            elif kind == "salida_tecnico":
                vals.update(mirabilenet_technician_id=technician.id,
                            mirabilenet_warehouse_id=source.id)
            elif kind == "asignacion_cliente":
                vals.update(mirabilenet_partner_id=partner.id, mirabilenet_technician_id=False)
            elif kind == "baja":
                vals.update(mirabilenet_technician_id=False, mirabilenet_partner_id=False)
            lot.write(vals)
        self.env["mirabilenet.audit.log"]._log(
            "inventario_mover",
            "%s de %s x%s" % (dict(KINDS)[kind], product.default_code or product.name,
                              quantity),
            record=move, region=region, payload={"motivo": reason, "serie": lot.name or ""})
        return move.with_env(self.env)

    def write(self, vals):
        if not self.env.su and any(m.mirabilenet_kind and m.state == "done" for m in self):
            raise UserError(_(
                "Un movimiento de inventario hecho no se edita: se revierte con otro."))
        return super().write(vals)

    def unlink(self):
        if any(m.mirabilenet_kind for m in self) and not self.env.su:
            raise UserError(_("Los movimientos de inventario no se eliminan."))
        return super().unlink()
