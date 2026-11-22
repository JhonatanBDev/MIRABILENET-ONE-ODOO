import base64

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

from ..models.ir_attachment import ALLOWED_EXTENSIONS, MAX_BYTES, check_file

PDF = base64.b64encode(b"%PDF-1.4 entrega de prueba").decode()
REPORT = {name: "Texto" for name in ("goal", "summary", "procedure", "tools", "parameters",
                                     "results", "rationale")}


@tagged("mirabilenet", "post_install", "-at_install")
class TestPasantias(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Region = cls.env["mirabilenet.region"]
        cls.norte = Region.create({"code": "P-N", "name": "Norte pasantías", "wg_region_id": 49})
        cls.sur = Region.create({"code": "P-S", "name": "Sur pasantías", "wg_region_id": 50})
        cls.tutor = cls._user("p_tutor_n", "tecnico", cls.norte)
        cls.tutor_s = cls._user("p_tutor_s", "tecnico", cls.sur)
        cls.vendedor = cls._user("p_vendedor", "vendedor", cls.norte)
        cls.ana = cls._user("p_ana", "pasante")
        cls.luis = cls._user("p_luis", "pasante")
        cls.project = cls.env["project.project"].with_user(cls.tutor).create(
            {"name": "Dron de práctica", "mirabilenet_internship": True})
        cls.task_ana = cls._task("Soporte del motor", cls.ana)
        cls.task_luis = cls._task("Soporte del motor", cls.luis)

    @classmethod
    def _user(cls, login, role, region=None):
        user = new_test_user(cls.env, login, groups="base.group_user")
        user.write({"mirabilenet_role": role,
                    "mirabilenet_region_id": region.id if region else False})
        return user

    @classmethod
    def _task(cls, name, intern, published=True, **values):
        data = {"name": name, "project_id": cls.project.id, "user_ids": [(6, 0, intern.ids)],
                "mirabilenet_published": published, "child_ids": [
                    (0, 0, {"name": "Medir el eje", "project_id": cls.project.id}),
                    (0, 0, {"name": "Exportar el plano", "project_id": cls.project.id}),
                    (0, 0, {"name": "Foto del prototipo", "project_id": cls.project.id,
                            "mirabilenet_required": False})]}
        data.update(values)
        return cls.env["project.task"].with_user(cls.tutor).create(data)

    def _done(self, task, user, only_required=True):
        points = task.with_user(user).child_ids
        (points.filtered("mirabilenet_required") if only_required else points).write(
            {"state": "1_done"})

    def _attach(self, task, user, name="soporte.step"):
        return self.env["ir.attachment"].with_user(user).create(
            {"name": name, "datas": PDF, "res_model": "project.task", "res_id": task.id})

    def test_project_uses_the_internship_stages(self):
        self.assertEqual(self.project.privacy_visibility, "followers")
        self.assertEqual(len(self.project.type_ids), 4)
        self.assertEqual(self.project.mirabilenet_region_id, self.norte)
        self.assertEqual(self.task_ana.mirabilenet_region_id, self.norte)
        self.assertTrue(self.tutor.has_group("mirabilenet_pasantias.group_internship_tutor"))
        self.assertTrue(self.ana.has_group("mirabilenet_pasantias.group_internship_intern"))

    def test_intern_sees_only_own_published_work(self):
        Task = self.env["project.task"].with_user(self.ana)
        seen = Task.search([("project_id", "=", self.project.id)])
        self.assertEqual(seen, self.task_ana | self.task_ana.child_ids)
        with self.assertRaises(AccessError):
            self.task_luis.with_user(self.ana).read(["name"])
        hidden = self._task("Borrador", self.ana, published=False)
        self.assertNotIn(hidden, Task.search([]))
        hidden.with_user(self.tutor).mirabilenet_published = True
        self.assertIn(hidden, Task.search([]))
        # Con Ventas instalado, un vendedor tiene acceso a Proyecto, pero no a esta tarea.
        self.assertFalse(self.env["project.task"].with_user(self.vendedor).search(
            [("id", "=", self.task_ana.id)]))
        self.assertFalse(self.env["project.task"].with_user(self.tutor_s).search(
            [("id", "=", self.task_ana.id)]))

    def test_intern_cannot_create_or_move_work(self):
        Task = self.env["project.task"].with_user(self.ana)
        with self.assertRaises(AccessError):
            Task.create({"name": "Mía", "project_id": self.project.id})
        own = self.task_ana.with_user(self.ana)
        for vals in ({"stage_id": self.env.ref("mirabilenet_pasantias.stage_approved").id},
                     {"state": "03_approved"}, {"state": "1_done"},
                     {"user_ids": [(4, self.luis.id)]}, {"name": "Otro"}):
            with self.assertRaises(AccessError, msg=vals):
                own.write(vals)
        with self.assertRaises(AccessError):
            own.child_ids[0].write({"state": "03_approved"})
        with self.assertRaises(AccessError):
            own.child_ids[0].unlink()

    def test_delivery_says_what_is_missing(self):
        task = self.task_ana.with_user(self.ana)
        task.child_ids[0].write({"state": "1_done"})
        with self.assertRaises(UserError) as caught:
            task.action_mirabilenet_deliver()
        self.assertIn("Exportar el plano", str(caught.exception))
        self.assertNotIn("Foto del prototipo", str(caught.exception))
        with self.assertRaises(AccessError):
            self.task_luis.with_user(self.ana).action_mirabilenet_deliver()
        self._done(self.task_ana, self.ana)
        self.task_ana.with_user(self.tutor).write(
            {"mirabilenet_requires_files": True, "mirabilenet_requires_report": True})
        with self.assertRaisesRegex(UserError, "al menos un archivo"):
            task.action_mirabilenet_deliver()
        self._attach(self.task_ana, self.ana)
        with self.assertRaisesRegex(UserError, "Objetivo y alcance"):
            task.action_mirabilenet_deliver()
        task.action_mirabilenet_open_report()
        report = self.task_ana.mirabilenet_report_id.with_user(self.ana)
        report.write(dict(REPORT, parameters="- Diámetro: 8 mm\nTolerancia H7"))
        with self.assertRaisesRegex(UserError, "cuántas horas"):
            task.action_mirabilenet_deliver()
        report.hours = 6.5
        task.action_mirabilenet_deliver()
        self.assertEqual(self.task_ana.stage_id, self.env.ref("mirabilenet_pasantias.stage_delivered"))
        self.assertTrue(self.task_ana.mirabilenet_delivered_at)
        self.assertEqual(report._parameter_rows(), [("Diámetro", "8 mm"), ("Tolerancia H7", "")])
        with self.assertRaises(AccessError):
            report.write({"tutor_comment": "Me apruebo"})

    def test_review_flow(self):
        task = self.task_ana
        with self.assertRaises(UserError):
            task.with_user(self.tutor)._mirabilenet_review(True)
        self._done(task, self.ana)
        task.with_user(self.ana).action_mirabilenet_deliver()
        with self.assertRaises(AccessError):
            task.with_user(self.ana)._mirabilenet_review(True)
        with self.assertRaises(AccessError):
            task.with_user(self.tutor_s)._mirabilenet_review(True)
        with self.assertRaises(UserError):
            task.with_user(self.tutor)._mirabilenet_review(False, "  ")
        task.with_user(self.tutor)._mirabilenet_review(False, "Falta la cota del eje")
        self.assertEqual((task.state, task.stage_id),
                         ("02_changes_requested", self.env.ref("mirabilenet_pasantias.stage_doing")))
        self.assertEqual(task.mirabilenet_report_id.tutor_comment, "Falta la cota del eje")
        task.with_user(self.ana).action_mirabilenet_deliver()
        self.env["mirabilenet.internship.review.wizard"].with_user(self.tutor).create(
            {"task_id": task.id, "verdict": "aprobar"}).action_apply()
        self.assertEqual(task.state, "03_approved")
        with self.assertRaises(UserError):
            task.child_ids[0].with_user(self.ana).write({"state": "01_in_progress"})
        with self.assertRaises(UserError):
            task.with_user(self.tutor)._mirabilenet_review(False, "Rehacer")
        task.with_user(self.tutor)._mirabilenet_review(False, "Rehacer", confirm_reopen=True)
        self.assertEqual(task.state, "02_changes_requested")
        log = self.env["mirabilenet.audit.log"].search(
            [("model", "=", "project.task"), ("res_id", "=", task.id)])
        self.assertEqual(len(log), 5)
        mine = self.tutor.copy({"login": "p_tutor_propio"})
        own = self._task("Propia", mine)
        with self.assertRaises(AccessError):
            own.with_user(mine)._mirabilenet_review(True)

    def test_files(self):
        first = self._attach(self.task_ana, self.ana, "foto.jpg")
        kept = self._attach(self.task_ana, self.ana, "informe.pdf")
        for bad in ("pagina.html", "pagina.HTM", "dibujo.svg", "programa.exe", "sin_extension"):
            with self.assertRaises(ValidationError, msg=bad):
                self._attach(self.task_ana, self.ana, bad)
        with self.assertRaises(AccessError):
            self._attach(self.task_luis, self.ana, "ajeno.pdf")
        first.with_user(self.ana).unlink()
        self._done(self.task_ana, self.ana)
        self.task_ana.with_user(self.ana).action_mirabilenet_deliver()
        self.task_ana.with_user(self.tutor)._mirabilenet_review(True)
        with self.assertRaisesRegex(UserError, "ya está aprobada"):
            kept.with_user(self.ana).unlink()
        with self.assertRaises(UserError):
            self._attach(self.task_ana, self.ana, "tarde.pdf")
        self.assertTrue(kept.exists())
        self.assertFalse({".html", ".htm", ".svg"} & ALLOWED_EXTENSIONS)
        self.assertEqual(MAX_BYTES, 90 * 1024 * 1024)
        with self.assertRaises(ValidationError):
            check_file("plano.dwg", MAX_BYTES + 1)

    def test_team_work_shares_only_delivered_files(self):
        attachment = self._attach(self.task_luis, self.luis, "pieza.stl")
        Attachment = self.env["ir.attachment"].with_user(self.ana)
        with self.assertRaises(AccessError):
            attachment.with_user(self.ana).read(["name"])
        self._done(self.task_luis, self.luis)
        self.task_luis.with_user(self.luis).action_mirabilenet_open_report()
        report = self.task_luis.mirabilenet_report_id
        report.with_user(self.luis).write({"goal": "Evaluación privada"})
        self.task_luis.with_user(self.luis).action_mirabilenet_deliver()
        self.assertEqual(self.task_luis.with_user(self.ana).read(["name"])[0]["name"],
                         "Soporte del motor")
        self.assertEqual(Attachment.search([("id", "=", attachment.id)]), attachment)
        with self.assertRaises(AccessError):
            report.with_user(self.ana).read(["goal"])
        with self.assertRaises(AccessError):
            self.task_luis.with_user(self.ana).action_mirabilenet_open_report()
        with self.assertRaises(AccessError):
            self.task_luis.with_user(self.ana).write({"state": "1_done"})
        with self.assertRaises(AccessError):
            attachment.with_user(self.ana).unlink()
        self.task_luis.with_user(self.tutor)._mirabilenet_review(False, "Corrija la base")
        with self.assertRaises(AccessError):
            attachment.with_user(self.ana).read(["name"])

    def test_report_renders(self):
        self.task_ana.with_user(self.ana).action_mirabilenet_open_report()
        report = self.task_ana.mirabilenet_report_id
        report.with_user(self.ana).write({"goal": "Diseñar el soporte", "parameters": "Material: PETG"})
        html = self.env["ir.actions.report"].with_user(self.ana)._render_qweb_html(
            "mirabilenet_pasantias.report_progress", report.ids)[0].decode()
        for expected in ("Soporte del motor", "Diseñar el soporte", "PETG", "Informe de avance"):
            self.assertIn(expected, html)
