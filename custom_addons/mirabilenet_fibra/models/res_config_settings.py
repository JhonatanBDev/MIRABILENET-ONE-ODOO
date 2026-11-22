from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mirabilenet_fiber_default_port_count = fields.Integer(
        string="Puertos por caja NAP", default=8,
        config_parameter="mirabilenet_fibra.default_port_count",
        help="Puertos con los que nace cada caja nueva (de 8 a 16).")
    mirabilenet_fiber_low_occupancy_threshold = fields.Integer(
        string="Umbral de baja ocupación (%)", default=30,
        config_parameter="mirabilenet_fibra.low_occupancy_threshold",
        help="Las zonas con ocupación por debajo de este porcentaje aparecen en "
             "«Zonas con pocos clientes».")

    @api.constrains("mirabilenet_fiber_default_port_count")
    def _check_mirabilenet_fiber_default_port_count(self):
        for settings in self:
            if not 8 <= settings.mirabilenet_fiber_default_port_count <= 16:
                raise ValidationError(_("Una caja NAP tiene de 8 a 16 puertos."))

    def action_mirabilenet_apply_standard_ports(self):
        self.execute()
        changed = self.env["mirabilenet.fiber.nap"]._mirabilenet_apply_standard_ports()
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"type": "success", "sticky": False,
                           "message": _("%s cajas NAP quedaron con los puertos estándar.",
                                        changed)}}
