from odoo import api, fields, models, _


class MirabilenetWhatsappOptout(models.Model):
    """Cliente que pidió no recibir más mensajes. Nunca se le vuelve a escribir."""
    _name = "mirabilenet.whatsapp.optout"
    _description = "MIRABILENET: baja de WhatsApp"
    _inherit = ["mirabilenet.region.scoped"]
    _order = "id desc"
    _rec_name = "partner_id"
    _region_path = ("partner_id",)

    partner_id = fields.Many2one(
        "res.partner", string="Cliente", required=True, ondelete="cascade", index=True,
        domain="[('mirabilenet_is_customer', '=', True)]")
    region_id = fields.Many2one(related="partner_id.mirabilenet_region_id", store=True,
                                index=True, string="Región")
    reason = fields.Char(string="Motivo")
    origin = fields.Selection(
        [("cliente", "Respondió BAJA"), ("panel", "Lo dio de baja un operador")],
        string="Origen", default="panel", required=True)

    _partner_uniq = models.Constraint("unique(partner_id)", "Ese cliente ya está dado de baja.")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Lo que estaba pendiente para ese cliente ya no sale.
        self.env["mirabilenet.whatsapp.message"].sudo().search([
            ("partner_id", "in", records.mapped("partner_id").ids),
            ("state", "=", "pendiente"),
        ]).write({"state": "descartado", "error_detail": _("Cliente dado de baja.")})
        return records

    @api.model
    def _opt_out(self, partner, reason="", origin="cliente"):
        """Registra la baja si no existía. Devuelve (baja, creada)."""
        existing = self.sudo().search([("partner_id", "=", partner.id)], limit=1)
        if existing:
            return existing, False
        return self.sudo().create({"partner_id": partner.id, "reason": (reason or "")[:200],
                                   "origin": origin}), True
