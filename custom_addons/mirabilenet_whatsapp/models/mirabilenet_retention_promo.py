from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class MirabilenetRetentionPromo(models.Model):
    """Oferta que el asistente puede hacer solo cuando un cliente quiere darse de baja. La
    ofrece el asistente; aplicarla es de una persona. Lo que no está aquí no existe."""
    _name = "mirabilenet.retention.promo"
    _description = "MIRABILENET: promoción de retención"
    _inherit = ["mirabilenet.region.scoped"]
    _order = "sequence, name"

    name = fields.Char(string="Nombre", required=True)
    offer = fields.Char(
        string="Qué se le ofrece al cliente", required=True,
        help="Tal como se lo diría el asistente, por ejemplo: 20 % de descuento en tu "
             "mensualidad por 3 meses.")
    conditions = fields.Char(string="Condiciones")
    region_id = fields.Many2one("mirabilenet.region", string="Región", ondelete="restrict",
                                index=True, help="Vacía: vale para todas las regiones.")
    date_from = fields.Date(string="Vigente desde")
    date_to = fields.Date(string="Vigente hasta")
    active = fields.Boolean(string="Activa", default=True)
    sequence = fields.Integer(string="Orden", default=0)

    _dates_check = models.Constraint(
        "CHECK(date_to IS NULL OR date_from IS NULL OR date_to >= date_from)",
        "«Vigente hasta» debe ser posterior a «vigente desde».")

    @api.model_create_multi
    def create(self, vals_list):
        # Al crear, no indicar región es pedir «todas las regiones».
        self._check_global_promo([dict(vals, region_id=vals.get("region_id"))
                                  for vals in vals_list])
        return super().create(vals_list)

    def write(self, vals):
        self._check_global_promo([vals])
        return super().write(vals)

    def _check_global_promo(self, vals_list):
        """Una promoción para todas las regiones solo la carga un usuario con alcance global."""
        user = self.env.user
        if self.env.su or user.mirabilenet_is_global or user._mirabilenet_is_super():
            return
        if any("region_id" in v and not v["region_id"] for v in vals_list) or any(
                not p.region_id for p in self.sudo()):
            raise AccessError(_(
                "Una promoción para todas las regiones la administra un usuario con alcance "
                "global."))

    @api.model
    def _current_for(self, region, today=None):
        today = today or self.env["account.move"]._mirabilenet_today()
        return self.sudo().search([
            "|", ("region_id", "=", region.id), ("region_id", "=", False),
            "|", ("date_from", "=", False), ("date_from", "<=", today),
            "|", ("date_to", "=", False), ("date_to", ">=", today)])
