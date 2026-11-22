from odoo import fields, models


class MirabilenetInternshipReviewWizard(models.TransientModel):
    _name = "mirabilenet.internship.review.wizard"
    _description = "MIRABILENET: revisar una entrega"

    task_id = fields.Many2one("project.task", required=True, readonly=True)
    verdict = fields.Selection([("aprobar", "Aprobar"), ("cambios", "Pedir cambios")],
                               string="Decisión", required=True, default="aprobar")
    comment = fields.Text(string="Devolución")
    confirm_reopen = fields.Boolean(string="Confirmo que quiero reabrir una tarea ya aprobada")

    def action_apply(self):
        self.ensure_one()
        self.task_id._mirabilenet_review(self.verdict == "aprobar", self.comment,
                                         self.confirm_reopen)
        return {"type": "ir.actions.act_window_close"}
