from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MirabilenetService(models.Model):
    _inherit = "mirabilenet.service"

    fiber_port_ids = fields.One2many("mirabilenet.fiber.port", "service_id",
                                     string="Puertos de fibra")
    fiber_nap_id = fields.Many2one(
        "mirabilenet.fiber.nap", string="NAP", compute="_compute_fiber_nap_id", store=True,
        readonly=False, index=True, domain="[('region_id', '=', region_id)]",
        help="Elija la NAP y luego un puerto libre de ella.")
    fiber_port_id = fields.Many2one(
        "mirabilenet.fiber.port", string="Puerto", compute="_compute_fiber_port_id",
        inverse="_inverse_fiber_port_id", store=True, index=True,
        domain="[('nap_id', '=', fiber_nap_id), ('state', '=', 'libre')]")
    fiber_maintenance_count = fields.Integer(string="Averías",
                                             compute="_compute_fiber_maintenance_count")

    @api.depends("fiber_port_ids")
    def _compute_fiber_port_id(self):
        for service in self:
            service.fiber_port_id = service.fiber_port_ids[:1]

    @api.depends("fiber_port_ids.nap_id")
    def _compute_fiber_nap_id(self):
        for service in self:
            service.fiber_nap_id = service.fiber_port_ids[:1].nap_id

    def _inverse_fiber_port_id(self):
        for service in self:
            new = service.fiber_port_id
            old = service.fiber_port_ids - new
            if old:
                old.write({"service_id": False})
            if new and new.service_id != service:
                if new.state not in ("libre", "reservado"):
                    raise UserError(_("El puerto %s no está libre.", new.display_name))
                new.write({"service_id": service.id})

    @api.onchange("fiber_nap_id")
    def _onchange_fiber_nap_id(self):
        if self.fiber_port_id and self.fiber_port_id.nap_id != self.fiber_nap_id:
            self.fiber_port_id = False

    def _compute_fiber_maintenance_count(self):
        Request = self.env["maintenance.request"]
        for service in self:
            service.fiber_maintenance_count = Request.search_count(
                [("mirabilenet_service_id", "=", service.id)])

    def action_mirabilenet_fiber_locate(self):
        """Caja, puerto, cómo llegar y estado de los vecinos de este servicio."""
        self.ensure_one()
        return self.env["mirabilenet.fiber.locate"].action_open_from_service(self)

    def write(self, vals):
        result = super().write(vals)
        if vals.get("state") == "baja":
            # Un servicio de baja deja su puerto libre para otro cliente.
            ports = self.filtered(lambda s: s.state == "baja").fiber_port_ids
            if ports:
                ports.write({"service_id": False})
                for port in ports:
                    port.message_post(body=_("Liberado por la baja del servicio."))
        return result

    def action_view_fiber_maintenance(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Averías de %s", self.display_name),
            "res_model": "maintenance.request",
            "view_mode": "list,form",
            "domain": [("mirabilenet_service_id", "=", self.id)],
            "context": {"default_mirabilenet_service_id": self.id,
                        "default_maintenance_type": "corrective",
                        "default_name": _("Avería de %s", self.display_name)},
        }

    def action_open_fiber_map(self):
        self.ensure_one()
        if not self.fiber_nap_id:
            raise UserError(_("El servicio no tiene NAP asignada."))
        return self.fiber_nap_id.action_open_map()
