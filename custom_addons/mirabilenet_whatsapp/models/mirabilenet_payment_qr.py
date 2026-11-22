import secrets

from odoo import api, fields, models


class MirabilenetPaymentQr(models.Model):
    """QR permanente de cobro de una región. Uno vigente; los anteriores quedan."""
    _name = "mirabilenet.payment.qr"
    _description = "MIRABILENET: QR de pago regional"
    _inherit = ["mirabilenet.region.scoped"]
    _order = "region_id, id desc"

    region_id = fields.Many2one("mirabilenet.region", string="Región", required=True,
                                ondelete="restrict", index=True)
    image = fields.Image(string="Imagen del QR", required=True, attachment=True)
    active = fields.Boolean(string="Vigente", default=True, index=True)
    user_id = fields.Many2one("res.users", string="Subido por", readonly=True,
                              default=lambda self: self.env.user)
    token = fields.Char(readonly=True, copy=False, index=True, groups="base.group_system",
                        default=lambda self: secrets.token_urlsafe(24))
    public_url = fields.Char(string="Dirección pública", compute="_compute_public_url")

    def _compute_public_url(self):
        base = (self.env["ir.config_parameter"].sudo().get_param(
            "mirabilenet.messaging_public_url")
            or self.env["ir.config_parameter"].sudo().get_param("web.base.url") or "")
        for qr in self.sudo():
            # El nombre lleva una clave que no se adivina: es lo único que separa el QR de
            # quien no debería verlo, porque Meta lo descarga sin sesión.
            qr.public_url = "%s/mirabilenet/qr/%s.png" % (base.rstrip("/"), qr.token)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for qr in records.filtered("active"):
            # El nuevo reemplaza al vigente; el anterior se conserva archivado.
            self.sudo().search([("region_id", "=", qr.region_id.id), ("active", "=", True),
                                ("id", "!=", qr.id)]).write({"active": False})
        return records

    @api.model
    def _current(self, region):
        return self.sudo().search([("region_id", "=", region.id), ("active", "=", True)],
                                  limit=1)
