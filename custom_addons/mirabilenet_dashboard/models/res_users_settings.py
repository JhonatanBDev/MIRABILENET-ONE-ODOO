from odoo import fields, models


class ResUsersSettings(models.Model):
    _inherit = "res.users.settings"

    # Lo que cada usuario eligió en el dashboard: filtros y tarjetas ocultas.
    mirabilenet_dashboard_prefs = fields.Json(string="Preferencias del dashboard")
