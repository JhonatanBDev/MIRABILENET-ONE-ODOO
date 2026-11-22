from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MirabilenetFiberSegmentStop(models.Model):
    """Paso de un tramo por una NAP, en el orden de la ruta."""
    _name = "mirabilenet.fiber.segment.stop"
    _description = "MIRABILENET: NAP en la ruta de un tramo"
    _order = "segment_id, sequence, id"

    sequence = fields.Integer(string="Orden", default=10)
    segment_id = fields.Many2one("mirabilenet.fiber.segment", string="Tramo", required=True,
                                 ondelete="cascade", index=True)
    nap_id = fields.Many2one("mirabilenet.fiber.nap", string="NAP", required=True,
                             ondelete="cascade", index=True,
                             domain="[('region_id', '=', region_id)]")
    region_id = fields.Many2one(related="segment_id.region_id", store=True, index=True,
                                string="Región")
    company_id = fields.Many2one(related="segment_id.company_id", store=True, index=True,
                                 string="Compañía")
    nap_name =fields.Char(related="nap_id.name", string="Nombre NAP")

    _segment_nap_uniq = models.Constraint(
        "unique(segment_id, nap_id)", "La NAP ya está en la ruta del tramo.")

    @api.constrains("segment_id", "nap_id")
    def _check_region(self):
        for stop in self:
            if stop.nap_id.region_id != stop.segment_id.region_id:
                raise ValidationError(_("La NAP y el tramo deben ser de la misma región."))
