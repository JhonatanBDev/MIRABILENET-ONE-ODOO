from odoo import api, fields, models

from .mirabilenet_web_published import slugify

PROJECT_KINDS = [("comunidad", "Comunidad"), ("empresa", "Empresa"), ("mina", "Minería"),
                 ("institucion", "Institución"), ("hogar", "Residencial")]


class MirabilenetWebProject(models.Model):
    _name = "mirabilenet.web.project"
    _description = "MIRABILENET: proyecto realizado"
    _inherit = ["mirabilenet.web.published"]
    _order = "sequence, date desc, id desc"
    _rec_name = "title"

    slug = fields.Char(string="Identificador", size=80, copy=False)
    title = fields.Char(string="Título", required=True, size=140)
    kind = fields.Selection(PROJECT_KINDS, string="Tipo", required=True, default="comunidad")
    summary = fields.Char(string="Resumen", required=True, size=220)
    description = fields.Text(string="Descripción")
    location = fields.Char(string="Ubicación", size=120)
    date = fields.Date(string="Fecha")
    image = fields.Image(string="Imagen")
    sequence = fields.Integer(string="Orden", default=0)
    active = fields.Boolean(string="Publicado", default=True)

    _slug_uniq = models.Constraint("unique(slug)", "Ya existe un proyecto con ese identificador.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals["slug"] = slugify(vals.get("slug") or vals.get("title"), 80)
        return super().create(vals_list)

    def write(self, vals):
        if "slug" in vals:
            vals["slug"] = slugify(vals["slug"] or vals.get("title") or self[:1].title, 80)
        return super().write(vals)
