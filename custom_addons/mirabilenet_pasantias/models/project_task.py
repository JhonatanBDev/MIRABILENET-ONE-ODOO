"""Pasantías con Proyecto y Empleados de Odoo. Una tarea por pasante; sus subtareas son la
lista de puntos. Aquí solo van las reglas que Odoo no trae."""
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

TUTOR = "mirabilenet_pasantias.group_internship_tutor"
INTERN = "mirabilenet_pasantias.group_internship_intern"
DONE, OPEN = "1_done", "01_in_progress"
#: Secciones del informe de avance: (campo, etiqueta, obligatoria).
REPORT_SECTIONS = (
    ("goal", "Objetivo y alcance", True), ("summary", "Resumen de lo realizado", True),
    ("procedure", "Procedimiento", True), ("tools", "Herramientas, software y materiales", True),
    ("parameters", "Parámetros y especificaciones técnicas", True),
    ("results", "Resultados y mediciones", True), ("validation", "Pruebas y validación", False),
    ("rationale", "Justificación técnica", True),
    ("difficulties", "Dificultades encontradas", False),
    ("next_steps", "Próximos pasos", False), ("references", "Referencias y normas", False),
)


def is_intern(env):
    return not env.su and env.user.has_group(INTERN) and not env.user.has_group(TUTOR)


class ProjectTask(models.Model):
    _inherit = "project.task"

    mirabilenet_internship = fields.Boolean(related="project_id.mirabilenet_internship",
                                            store=True)
    mirabilenet_region_id = fields.Many2one(related="project_id.mirabilenet_region_id",
                                            store=True, index=True, string="Región")
    mirabilenet_published = fields.Boolean(
        string="Publicada", copy=False,
        help="Asignar no es publicar: mientras no lo esté, el pasante no la ve.")
    mirabilenet_required = fields.Boolean(
        string="Punto obligatorio", default=True,
        help="En una subtarea: sin cumplirla, el pasante no puede entregar.")
    mirabilenet_requires_files = fields.Boolean(string="Pide archivos")
    mirabilenet_requires_report = fields.Boolean(string="Pide informe de avance")
    mirabilenet_delivered_at = fields.Datetime(string="Entregada el", readonly=True, copy=False)
    mirabilenet_report_id = fields.Many2one("mirabilenet.internship.report",
                                            string="Informe de avance", readonly=True,
                                            copy=False)

    # -- Reglas del pasante ------------------------------------------------
    def _mirabilenet_owned(self):
        """Cada tarea debe ser del pasante que actúa (o de una tarea suya, si es un punto)."""
        for task in self.sudo():
            main = task.parent_id or task
            if self.env.user not in main.user_ids:
                raise AccessError(_("Esta tarea no es suya."))
            if main.state == "03_approved":
                raise UserError(_("La tarea ya está aprobada; no se puede cambiar."))

    @api.model_create_multi
    def create(self, vals_list):
        if is_intern(self.env):
            raise AccessError(_("Un pasante no crea tareas ni se asigna trabajo."))
        return super().create(vals_list)

    def write(self, vals):
        if is_intern(self.env):
            allowed = {"state", "message_main_attachment_id"}
            if set(vals) - allowed or vals.get("state", DONE) not in (DONE, OPEN):
                raise AccessError(_(
                    "El estado de una entrega se mueve con «Entregar», y la tarea la arma el "
                    "tutor. Usted solo marca los puntos cumplidos."))
            if "state" in vals and any(not task.parent_id for task in self):
                raise AccessError(_("Solo se marcan los puntos de la lista."))
            self._mirabilenet_owned()
        return super().write(vals)

    def unlink(self):
        if is_intern(self.env):
            raise AccessError(_("Un pasante no elimina tareas."))
        return super().unlink()

    # -- Entrega y revisión -----------------------------------------------
    def _mirabilenet_missing_points(self):
        self.ensure_one()
        return self.sudo().child_ids.filtered(
            lambda t: t.mirabilenet_required and t.state != DONE).mapped("name")

    def action_mirabilenet_deliver(self):
        """Cierra la entrega. No se entrega a medias: se dice qué falta."""
        self.ensure_one()
        task = self.sudo()
        if self.env.user not in task.user_ids:
            raise AccessError(_("Esta tarea no es suya."))
        if task.stage_id == self.env.ref("mirabilenet_pasantias.stage_approved"):
            raise UserError(_("La tarea ya está aprobada."))
        if task.stage_id == self.env.ref("mirabilenet_pasantias.stage_delivered"):
            raise UserError(_("La tarea ya está entregada y en revisión."))
        missing = task._mirabilenet_missing_points()
        if missing:
            raise UserError(_("Faltan puntos obligatorios por cumplir:\n- %s",
                              "\n- ".join(missing)))
        if task.mirabilenet_requires_files and not self.env["ir.attachment"].sudo().search_count(
                [("res_model", "=", "project.task"), ("res_id", "=", task.id)]):
            raise UserError(_("Esta tarea pide subir al menos un archivo."))
        if task.mirabilenet_requires_report:
            report = task.mirabilenet_report_id
            sections = report._missing_sections() if report else [
                label for _n, label, required in REPORT_SECTIONS if required]
            if sections:
                raise UserError(_("El informe de avance está incompleto. Falta:\n- %s",
                                  "\n- ".join(sections)))
            if report.hours <= 0:
                raise UserError(_("El informe no dice cuántas horas dedicó."))
        task.write({"stage_id": self.env.ref("mirabilenet_pasantias.stage_delivered").id,
                    "state": OPEN, "mirabilenet_delivered_at": fields.Datetime.now()})
        self.env["mirabilenet.audit.log"]._log(
            "modificar", "%s entregó «%s»" % (self.env.user.name, task.name), record=task,
            region=task.mirabilenet_region_id)
        return True

    def _mirabilenet_review(self, approve, comment="", confirm_reopen=False):
        """Aprueba o pide cambios. Solo un tutor, y nunca sobre su propio trabajo."""
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group(TUTOR):
            raise AccessError(_("Solo un tutor revisa las entregas."))
        self.check_access("write")
        task = self.sudo()
        if self.env.user in task.user_ids:
            raise AccessError(_("Nadie aprueba su propio trabajo."))
        comment = (comment or "").strip()
        if not approve and not comment:
            raise UserError(_("Para pedir cambios hay que decir cuáles."))
        approved_stage = self.env.ref("mirabilenet_pasantias.stage_approved")
        if approve and task.stage_id != self.env.ref("mirabilenet_pasantias.stage_delivered"):
            raise UserError(_("Todavía no hay una entrega que aprobar."))
        reopening = task.stage_id == approved_stage and not approve
        if reopening and not confirm_reopen:
            raise UserError(_("Esta tarea ya estaba aprobada. Confirme que quiere reabrirla "
                              "para pedir cambios."))
        task.write({
            "stage_id": (approved_stage if approve else
                         self.env.ref("mirabilenet_pasantias.stage_doing")).id,
            "state": "03_approved" if approve else "02_changes_requested"})
        # La devolución va al informe, que solo ven el pasante y los tutores.
        report = task._mirabilenet_ensure_report()
        verdict = (_("Aprobación revertida: se piden cambios") if reopening
                   else _("Trabajo aprobado") if approve else _("Cambios pedidos"))
        report.tutor_comment = comment or report.tutor_comment
        report.message_post(body="%s. %s" % (verdict, comment) if comment else verdict,
                            author_id=self.env.user.partner_id.id,
                            partner_ids=task.user_ids.partner_id.ids)
        self.env["mirabilenet.audit.log"]._log(
            "modificar", "«%s»: %s" % (task.name, verdict.lower()), record=task,
            region=task.mirabilenet_region_id)
        return True

    def action_mirabilenet_review(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Revisar la entrega"),
                "res_model": "mirabilenet.internship.review.wizard", "view_mode": "form",
                "target": "new", "context": {"default_task_id": self.id}}

    def _mirabilenet_ensure_report(self):
        self.ensure_one()
        task = self.sudo()
        if not task.mirabilenet_report_id:
            task.mirabilenet_report_id = self.env["mirabilenet.internship.report"].sudo().create(
                {"task_id": task.id})
        return task.mirabilenet_report_id

    def action_mirabilenet_open_report(self):
        self.ensure_one()
        if is_intern(self.env) and self.env.user not in self.sudo().user_ids:
            raise AccessError(_("El informe es de quien hizo la tarea."))
        report = self._mirabilenet_ensure_report()
        return {"type": "ir.actions.act_window", "res_model": report._name, "res_id": report.id,
                "view_mode": "form", "target": "current"}
