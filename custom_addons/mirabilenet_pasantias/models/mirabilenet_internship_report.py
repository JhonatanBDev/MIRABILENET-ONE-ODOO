from odoo import fields, models, _
from odoo.exceptions import AccessError

from .project_task import REPORT_SECTIONS, is_intern


class MirabilenetInternshipReport(models.Model):
    """El informe de avance de una tarea. Lo ven solo el pasante y los tutores: es la
    evaluación, no el material que se comparte con el equipo."""
    _name = "mirabilenet.internship.report"
    _description = "MIRABILENET: informe de avance"
    _inherit = ["mail.thread"]
    _rec_name = "task_id"

    task_id = fields.Many2one("project.task", string="Tarea", required=True, readonly=True,
                              ondelete="cascade", index=True)
    intern_ids = fields.Many2many(related="task_id.user_ids", string="Pasante")
    region_id = fields.Many2one(related="task_id.mirabilenet_region_id", store=True,
                                string="Región")
    goal = fields.Text(string="Objetivo y alcance")
    summary = fields.Text(string="Resumen de lo realizado")
    procedure = fields.Text(string="Procedimiento")
    tools = fields.Text(string="Herramientas, software y materiales")
    parameters = fields.Text(string="Parámetros y especificaciones técnicas",
                             help="Uno por línea, con la forma «nombre: valor».")
    results = fields.Text(string="Resultados y mediciones")
    validation = fields.Text(string="Pruebas y validación")
    rationale = fields.Text(string="Justificación técnica")
    difficulties = fields.Text(string="Dificultades encontradas")
    next_steps = fields.Text(string="Próximos pasos")
    references = fields.Text(string="Referencias y normas")
    hours = fields.Float(string="Horas dedicadas", digits=(6, 1))
    tutor_comment = fields.Text(string="Devolución del tutor", readonly=True)

    _task_uniq = models.Constraint("unique(task_id)", "Esa tarea ya tiene su informe.")

    def write(self, vals):
        if is_intern(self.env):
            if "tutor_comment" in vals:
                raise AccessError(_("La devolución la escribe el tutor."))
            self.mapped("task_id")._mirabilenet_owned()
        return super().write(vals)

    def _missing_sections(self):
        self.ensure_one()
        return [label for name, label, required in REPORT_SECTIONS
                if required and not (self[name] or "").strip()]

    def _parameter_rows(self):
        self.ensure_one()
        rows = []
        for line in (self.parameters or "").splitlines():
            line = line.strip().lstrip("-•*").strip()
            if line:
                name, separator, value = line.partition(":")
                rows.append((name.strip(), value.strip()) if separator else (line, ""))
        return rows

    def _sections(self):
        self.ensure_one()
        return [(label, self[name]) for name, label, _r in REPORT_SECTIONS
                if name != "parameters" and (self[name] or "").strip()]
