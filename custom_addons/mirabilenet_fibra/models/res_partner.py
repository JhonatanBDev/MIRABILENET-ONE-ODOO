from odoo import _, api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    mirabilenet_fiber_port_ids = fields.One2many(
        "mirabilenet.fiber.port", "partner_id", string="Puertos de fibra",
        help="Puertos asignados a los servicios del cliente.")
    mirabilenet_fiber_port_count = fields.Integer(
        string="NAP/Puerto", compute="_compute_mirabilenet_fiber_port")
    mirabilenet_fiber_summary = fields.Char(
        string="NAP y puerto", compute="_compute_mirabilenet_fiber_port")

    @api.depends("mirabilenet_fiber_port_ids")
    def _compute_mirabilenet_fiber_port(self):
        for partner in self:
            ports = partner.mirabilenet_fiber_port_ids
            partner.mirabilenet_fiber_port_count = len(ports)
            partner.mirabilenet_fiber_summary = ", ".join(
                "%s P%s" % (p.nap_id.name or p.nap_id.code, p.number) for p in ports)

    def action_view_mirabilenet_fiber_ports(self):
        self.ensure_one()
        ports = self.mirabilenet_fiber_port_ids
        action = {
            "type": "ir.actions.act_window",
            "name": _("NAP/Puerto de %s", self.display_name),
            "res_model": "mirabilenet.fiber.port",
            "view_mode": "list,form",
            "domain": [("id", "in", ports.ids)],
        }
        if len(ports) == 1:
            action.update({"view_mode": "form", "res_id": ports.id})
        return action
