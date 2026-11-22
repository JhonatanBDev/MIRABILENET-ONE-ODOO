from odoo import fields, models


class ProjectTaskType(models.Model):
    _inherit = "project.task.type"

    mirabilenet_shared = fields.Boolean(
        string="Se comparte con el equipo",
        help="Las tareas en esta etapa ya están presentadas: los demás pasantes del proyecto "
             "ven sus archivos.")
