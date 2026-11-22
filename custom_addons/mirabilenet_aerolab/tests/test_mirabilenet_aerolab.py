from datetime import datetime, timedelta

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

from ..aerolab import contenido_inicial as C


@tagged("mirabilenet", "post_install", "-at_install")
class TestAerolab(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Region = cls.env["mirabilenet.region"]
        cls.norte = Region.create({"code": "A-N", "name": "Norte cursos", "wg_region_id": 51})
        cls.sur = Region.create({"code": "A-S", "name": "Sur cursos", "wg_region_id": 52})
        cls.gerencia = cls._user("a_gerencia", "gerencia")
        cls.admin_n = cls._user("a_admin_n", "admin_regional", cls.norte)
        cls.vendedor_n = cls._user("a_vendedor_n", "vendedor", cls.norte)
        cls.vendedor_s = cls._user("a_vendedor_s", "vendedor", cls.sur)
        cls.question = cls.env.ref("mirabilenet_aerolab.question_ci")
        start = datetime.now() + timedelta(days=20)
        cls.course = cls.env["event.event"].create({
            "name": "Pilotaje Básico", "mirabilenet_region_id": cls.norte.id,
            "date_begin": start, "date_end": start + timedelta(hours=4)})

    @classmethod
    def _user(cls, login, role, region=None):
        user = new_test_user(cls.env, login, groups="base.group_user")
        user.write({"mirabilenet_role": role,
                    "mirabilenet_region_id": region.id if region else False})
        return user

    def _register(self, ci, event=None, cancelled=False):
        registration = self.env["event.registration"].create({
            "event_id": (event or self.course).id, "name": "Persona %s" % ci})
        self.env["event.registration.answer"].create({
            "registration_id": registration.id, "question_id": self.question.id,
            "value_text_box": ci})
        if cancelled:
            registration.action_cancel()
        return registration

    def test_course_stays_in_preparation_until_complete(self):
        course = self.course
        self.assertIn(self.question, course.question_ids, "el carnet se pide en todo curso")
        self.assertEqual(course.mirabilenet_missing,
                         "fecha confirmada, cupo, precio (una entrada con precio)")
        with self.assertRaises(ValidationError) as caught:
            course.website_published = True
        self.assertIn("no se inventan", str(caught.exception))
        course.write({"mirabilenet_date_confirmed": True, "seats_limited": True,
                      "seats_max": 12})
        with self.assertRaises(ValidationError):
            course.website_published = True
        course.write({"event_ticket_ids": [(0, 0, {"name": "General", "price": 800})]})
        course.website_published = True
        self.assertFalse(course.mirabilenet_missing)
        with self.assertRaises(ValidationError):
            course.event_ticket_ids.price = 0
        with self.assertRaises(ValidationError):
            course.event_ticket_ids.unlink()

    def test_one_ci_per_course(self):
        self._register("1234567")
        with self.assertRaises(ValidationError):
            self._register(" 1234 567 ")
        other = self.course.copy({"name": "Fotogrametría"})
        self._register("1234567", event=other)
        cancelled = self._register("7654321", event=other, cancelled=True)
        self.assertEqual(cancelled.state, "cancel")
        self._register("7654321", event=other)

    def test_courses_are_isolated_by_region(self):
        Event = self.env["event.event"]
        self.assertEqual(Event.with_user(self.vendedor_n).search([("id", "=", self.course.id)]),
                         self.course)
        self.assertFalse(Event.with_user(self.vendedor_s).search([("id", "=", self.course.id)]))
        with self.assertRaises(AccessError):
            self.course.with_user(self.vendedor_s).read(["name"])
        self.assertTrue(Event.with_user(self.gerencia).search([("id", "=", self.course.id)]))
        registration = self._register("1111111")
        Registration = self.env["event.registration"]
        self.assertFalse(Registration.with_user(self.vendedor_s).search(
            [("id", "=", registration.id)]))
        self.assertTrue(self.vendedor_n.has_group("event.group_event_user"))
        self.assertTrue(self.admin_n.has_group("event.group_event_manager"))
        # El público ve los cursos publicados, sea cual sea su región.
        self.course.write({"mirabilenet_date_confirmed": True, "seats_limited": True,
                           "seats_max": 5,
                           "event_ticket_ids": [(0, 0, {"name": "General", "price": 500})],
                           "website_published": True})
        public = self.env.ref("base.public_user")
        self.assertEqual(Event.with_user(public).search([("id", "=", self.course.id)]),
                         self.course)

    def test_initial_courses_arrive_unpublished(self):
        created = self.env["event.event"]._mirabilenet_load_initial_courses()
        self.assertEqual(len(created), len(C.CURSOS))
        self.assertFalse(any(created.mapped("website_published")))
        self.assertFalse(any(created.mapped("mirabilenet_date_confirmed")))
        self.assertFalse(created.mapped("event_ticket_ids").filtered("price"))
        self.assertTrue(all(len(c.tag_ids) == 2 for c in created))
        self.assertFalse(self.env["event.event"]._mirabilenet_load_initial_courses())
