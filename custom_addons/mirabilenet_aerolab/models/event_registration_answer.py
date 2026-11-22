from odoo import api, models, _
from odoo.exceptions import ValidationError

CI_QUESTION = "mirabilenet_aerolab.question_ci"


def normalize_ci(value):
    return "".join((value or "").split()).upper()


class EventRegistrationAnswer(models.Model):
    _inherit = "event.registration.answer"

    @api.constrains("value_text_box", "question_id", "registration_id")
    def _check_mirabilenet_ci_once_per_course(self):
        """Un mismo carnet no se inscribe dos veces al mismo curso."""
        question = self.env.ref(CI_QUESTION, raise_if_not_found=False)
        Answer = self.sudo()
        for answer in self.sudo().filtered(lambda a: a.question_id == question):
            ci = normalize_ci(answer.value_text_box)
            if not ci:
                continue
            others = Answer.search([
                ("id", "!=", answer.id), ("question_id", "=", question.id),
                ("registration_id.event_id", "=", answer.registration_id.event_id.id),
                ("registration_id.state", "!=", "cancel")])
            if any(normalize_ci(other.value_text_box) == ci for other in others):
                raise ValidationError(_(
                    "Este carnet ya figura inscrito en el curso. Escríbanos si necesita "
                    "cambiar sus datos."))
