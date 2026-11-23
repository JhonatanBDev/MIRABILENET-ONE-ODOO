from odoo import _, api, models


class ProjectTask(models.Model):
    """A quien le asignan una tarea (un pasante, un técnico, cualquiera del equipo) le llega
    por WhatsApp, con botones «Recibido» y «Terminada»."""
    _inherit = "project.task"

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        for task in tasks:
            task._mirabilenet_notify_assignees(task.user_ids)
        return tasks

    def write(self, vals):
        before = {t.id: t.user_ids for t in self} if "user_ids" in vals else {}
        # Una tarea de pasantía se avisa al publicarla: antes el pasante no la ve.
        unpublished = self.filtered(
            lambda t: t._mirabilenet_is_internship() and not t.mirabilenet_published)             if vals.get("mirabilenet_published") else self.browse()
        result = super().write(vals)
        for task in self:
            if task in unpublished:
                task._mirabilenet_notify_assignees(task.user_ids)
            elif task.id in before:
                task._mirabilenet_notify_assignees(task.user_ids - before[task.id])
        return result

    def _mirabilenet_is_internship(self):
        """Tarea de una pasantía (el campo solo existe con el módulo de pasantías)."""
        self.ensure_one()
        return "mirabilenet_internship" in self._fields and self.mirabilenet_internship

    def _mirabilenet_notify_assignees(self, users):
        self.ensure_one()
        # Solo el trabajo de un proyecto: las notas personales (como la tarea de bienvenida que
        # Odoo crea para cada usuario nuevo) no son trabajo asignado.
        if not self.project_id or self.is_closed:
            return
        users = (users - self.env.user)._mirabilenet_reachable() if users else users
        if not users:
            return
        deadline = self.date_deadline.strftime("%d/%m/%Y") if self.date_deadline else _("sin fecha")
        Notice = self.env["mirabilenet.staff.notice"]
        if self._mirabilenet_is_internship():
            # Solo la tarea principal y ya publicada; los puntos se ven dentro de ella.
            if self.parent_id or not self.mirabilenet_published:
                return
            Notice._notify(users, "tarea_pasante", {
                "tarea": self.name, "fecha_limite": deadline,
                "enlace": "%s/odoo/project.task/%d" % (self.get_base_url(), self.id)}, task=self)
            return
        values = {"tarea": self.name, "proyecto": self.project_id.name or "-",
                  "fecha_limite": deadline, "asignado_por": self.env.user.name}
        Notice._notify(users, "tarea_asignada", values, task=self)

    def _mirabilenet_apply_action(self, action, user):
        self.ensure_one()
        task = self.sudo()
        Notice = self.env["mirabilenet.staff.notice"]
        if action == "recibido":
            task.message_post(body=_("%s recibió la tarea (WhatsApp).", user.name))
            Notice._reply(user, _("Anotado: recibió «%s».", task.name))
            return "recibido"
        if action == "terminada" and task._mirabilenet_is_internship():
            Notice._reply(user, _("«%s» se entrega en la plataforma, con su informe.", task.name))
            return "en_plataforma"
        if action == "terminada":
            task.state = "1_done"
            task.message_post(body=_("%s marcó la tarea como terminada (WhatsApp).", user.name))
            Notice._reply(user, _("¡Gracias! «%s» quedó terminada.", task.name))
            return "terminada"
        return "desconocido"
