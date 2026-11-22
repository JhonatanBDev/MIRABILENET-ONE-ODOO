from odoo import fields, models


class MirabilenetNode(models.Model):
    _name = "mirabilenet.node"
    _description = "MIRABILENET: nodo"
    _inherit = ["mirabilenet.region.scoped"]
    _region_path = ("region_id", "zone_id")
    _order = "name"

    zone_id = fields.Many2one("mirabilenet.zone", string="Zona", required=True,
                              ondelete="restrict", index=True)
    region_id = fields.Many2one(related="zone_id.region_id", string="Región", store=True,
                                index=True)
    code = fields.Char(string="Código", required=True, size=20)
    name = fields.Char(string="Nombre", required=True)
    latitude = fields.Float(string="Latitud", digits=(9, 6))
    longitude = fields.Float(string="Longitud", digits=(9, 6))
    capacidad_instalada = fields.Integer(
        string="Capacidad instalada", help="Clientes que el nodo puede sostener.")
    active = fields.Boolean(string="Activo", default=True)

    _code_uniq = models.Constraint("unique(code)", "Ya existe un nodo con ese código.")
    _capacity_check = models.Constraint(
        "CHECK(capacidad_instalada >= 0)", "La capacidad instalada no puede ser negativa.")
