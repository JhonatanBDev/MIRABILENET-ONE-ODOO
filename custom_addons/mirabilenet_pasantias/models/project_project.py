from odoo import api, fields, models


class ProjectProject(models.Model):
    _inherit = "project.project"

    mirabilenet_internship = fields.Boolean(string="Proyecto de pasantías")
    mirabilenet_region_id = fields.Many2one(
        "mirabilenet.region", string="Región", index=True, ondelete="restrict",
        default=lambda self: self.env.user.mirabilenet_region_id)

    @api.model_create_multi
    def create(self, vals_list):
        stages = self.env.ref("mirabilenet_pasantias.stage_todo") | self.env.ref(
            "mirabilenet_pasantias.stage_doing") | self.env.ref(
            "mirabilenet_pasantias.stage_delivered") | self.env.ref(
            "mirabilenet_pasantias.stage_approved")
        for vals in vals_list:
            if vals.get("mirabilenet_internship"):
                vals.setdefault("type_ids", [(6, 0, stages.ids)])
                vals.setdefault("privacy_visibility", "followers")
        return super().create(vals_list)
