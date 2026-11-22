from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MaintenanceRequest(models.Model):
    """Avería de un cliente: el pedido de mantenimiento de Odoo, sin equipos."""
    _inherit = "maintenance.request"

    mirabilenet_service_id = fields.Many2one("mirabilenet.service", string="Servicio",
                                             index="btree_not_null", ondelete="set null")
    mirabilenet_partner_id = fields.Many2one(related="mirabilenet_service_id.partner_id",
                                             string="Cliente")
    mirabilenet_fiber_nap_id = fields.Many2one("mirabilenet.fiber.nap", string="NAP",
                                               index="btree_not_null", ondelete="set null")
    mirabilenet_fiber_port_id = fields.Many2one(
        "mirabilenet.fiber.port", string="Puerto", ondelete="set null",
        domain="[('nap_id', '=', mirabilenet_fiber_nap_id)]")

    @api.onchange("mirabilenet_service_id")
    def _onchange_mirabilenet_service_id(self):
        service = self.mirabilenet_service_id
        if service.fiber_port_id:
            self.mirabilenet_fiber_port_id = service.fiber_port_id
            self.mirabilenet_fiber_nap_id = service.fiber_port_id.nap_id
        elif service.fiber_nap_id:
            self.mirabilenet_fiber_nap_id = service.fiber_nap_id

    @api.onchange("mirabilenet_fiber_port_id")
    def _onchange_mirabilenet_fiber_port_id(self):
        if self.mirabilenet_fiber_port_id:
            self.mirabilenet_fiber_nap_id = self.mirabilenet_fiber_port_id.nap_id

    @api.model_create_multi
    def create(self, vals_list):
        Service = self.env["mirabilenet.service"]
        for vals in vals_list:
            if vals.get("mirabilenet_service_id") and not vals.get("mirabilenet_fiber_nap_id"):
                service = Service.browse(vals["mirabilenet_service_id"])
                vals.setdefault("mirabilenet_fiber_port_id", service.fiber_port_id.id)
                vals["mirabilenet_fiber_nap_id"] = service.fiber_nap_id.id
        return super().create(vals_list)

    def action_mirabilenet_fiber_locate(self):
        self.ensure_one()
        return self.env["mirabilenet.fiber.locate"].action_open_from_service(
            self.mirabilenet_service_id)

    def action_mirabilenet_fiber_map(self):
        self.ensure_one()
        if not self.mirabilenet_fiber_nap_id:
            raise UserError(_("La avería no tiene NAP."))
        return self.mirabilenet_fiber_nap_id.action_open_map()
