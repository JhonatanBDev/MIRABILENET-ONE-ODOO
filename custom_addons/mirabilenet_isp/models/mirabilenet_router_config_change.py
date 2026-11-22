from odoo import fields, models


class MirabilenetRouterConfigChange(models.Model):
    """Qué tocó cada guion en el router, para poder revertirlo."""
    _name = "mirabilenet.router.config.change"
    _description = "MIRABILENET: cambio de configuración del router"
    _order = "id desc"
    _rec_name = "kind"

    router_id = fields.Many2one("mirabilenet.router", string="Router", required=True,
                                ondelete="cascade", index=True, readonly=True)
    region_id = fields.Many2one(related="router_id.region_id", store=True, index=True)
    kind = fields.Char(string="Tipo de guion", required=True, readonly=True)
    summary = fields.Text(string="Resumen", readonly=True)
    data = fields.Json(string="Datos", readonly=True)
    backup_name = fields.Char(string="Respaldo previo", readonly=True)
