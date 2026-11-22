from odoo import _, fields, models
from odoo.exceptions import UserError


class MirabilenetFiberPortAssign(models.TransientModel):
    """Asignar cliente a puerto: el servicio del cliente queda en el puerto elegido."""
    _name = "mirabilenet.fiber.port.assign"
    _description = "MIRABILENET: asignar cliente a puerto"

    nap_id = fields.Many2one("mirabilenet.fiber.nap", string="NAP", required=True)
    region_id = fields.Many2one(related="nap_id.region_id")
    port_id = fields.Many2one(
        "mirabilenet.fiber.port", string="Puerto", required=True,
        domain="[('nap_id', '=', nap_id), ('state', 'in', ('libre', 'reservado'))]")
    service_id = fields.Many2one(
        "mirabilenet.service", string="Servicio", required=True,
        domain="[('region_id', '=', region_id), ('state', '!=', 'baja'), "
               "('fiber_port_id', '=', False)]")

    def action_assign(self):
        self.ensure_one()
        if self.port_id.state not in ("libre", "reservado"):
            raise UserError(_("El puerto %s ya no está libre.", self.port_id.display_name))
        self.port_id.write({"service_id": self.service_id.id})
        return {"type": "ir.actions.act_window_close"}
