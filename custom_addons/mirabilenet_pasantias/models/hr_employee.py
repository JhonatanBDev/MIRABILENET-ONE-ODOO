from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    mirabilenet_institution = fields.Char(string="Institución")
    mirabilenet_career = fields.Char(string="Carrera o área")
    mirabilenet_hours_committed = fields.Integer(string="Horas comprometidas")
