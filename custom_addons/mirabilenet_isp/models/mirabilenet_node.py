from odoo import api, fields, models

#: Estados que ocupan capacidad en el nodo.
COMMITTED_STATES = ("activo", "suspendido", "moroso")


class MirabilenetNode(models.Model):
    _inherit = "mirabilenet.node"

    service_ids = fields.One2many("mirabilenet.service", "node_id", string="Servicios")
    capacidad_comprometida = fields.Integer(
        string="Capacidad comprometida", compute="_compute_capacidad")
    capacidad_disponible = fields.Integer(
        string="Capacidad disponible", compute="_compute_capacidad")

    @api.depends("service_ids.state", "capacidad_instalada")
    def _compute_capacidad(self):
        for node in self:
            used = len(node.service_ids.filtered(lambda s: s.state in COMMITTED_STATES))
            node.capacidad_comprometida = used
            node.capacidad_disponible = max(node.capacidad_instalada - used, 0)
