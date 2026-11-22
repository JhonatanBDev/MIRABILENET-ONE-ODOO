from odoo import api, fields, models

from .mirabilenet_web_published import ICONS, slugify


class MirabilenetWebService(models.Model):
    _name = "mirabilenet.web.service"
    _description = "MIRABILENET: servicio del sitio"
    _inherit = ["mirabilenet.web.published"]
    _order = "sequence, name"

    slug = fields.Char(string="Identificador", size=60, copy=False,
                       help="Va en la dirección de la página. Vacío: se arma con el nombre.")
    name = fields.Char(string="Nombre", required=True, size=100)
    summary = fields.Char(string="Resumen", required=True, size=200)
    description = fields.Text(string="Descripción")
    benefits = fields.Text(string="Beneficios", help="Uno por línea.")
    icon = fields.Selection(ICONS, string="Icono", default="antena", required=True)
    featured = fields.Boolean(string="Destacado en la portada")
    sequence = fields.Integer(string="Orden", default=0)
    active = fields.Boolean(string="Activo", default=True)

    _slug_uniq = models.Constraint("unique(slug)", "Ya existe un servicio con ese identificador.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals["slug"] = slugify(vals.get("slug") or vals.get("name"), 60)
        return super().create(vals_list)

    def write(self, vals):
        if "slug" in vals:
            vals["slug"] = slugify(vals["slug"] or vals.get("name") or self[:1].name, 60)
        return super().write(vals)
