from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MirabilenetWhatsappConsent(models.Model):
    """Permiso del cliente para recibir mensajes. Meta lo exige antes de la primera
    plantilla, y hay que poder probarlo."""
    _name = "mirabilenet.whatsapp.consent"
    _description = "MIRABILENET: consentimiento de WhatsApp"
    _inherit = ["mirabilenet.region.scoped"]
    _order = "granted_at desc"
    _rec_name = "partner_id"
    _region_path = ("partner_id",)

    partner_id = fields.Many2one(
        "res.partner", string="Cliente", required=True, ondelete="cascade", index=True,
        domain="[('mirabilenet_is_customer', '=', True)]")
    region_id = fields.Many2one(related="partner_id.mirabilenet_region_id", store=True,
                                index=True, string="Región")
    origin = fields.Selection(
        [("contrato", "Cláusula del contrato firmado"),
         ("formulario", "Formulario web o de alta"),
         ("verbal", "Declarado en oficina o por teléfono"),
         ("mensaje", "Respondió aceptando por WhatsApp"),
         ("importacion", "Cargado desde registros previos")],
        string="Cómo consta", required=True,
        help="Es lo que habría que mostrar si se reclama.")
    detail = fields.Char(string="Detalle", required=True,
                         help="Número de contrato, fecha de la llamada, o lo que permita "
                              "ubicar la autorización.")
    granted_at = fields.Datetime(string="Otorgado", required=True, default=fields.Datetime.now)
    user_id = fields.Many2one("res.users", string="Registrado por", readonly=True,
                              default=lambda self: self.env.user)

    _partner_uniq = models.Constraint(
        "unique(partner_id)", "Ese cliente ya tiene un consentimiento registrado.")

    @api.model_create_multi
    def create(self, vals_list):
        # Nunca en lote por inferencia: cada permiso refleja una autorización real, con su
        # evidencia, y lo registra una persona.
        if len(vals_list) > 1 and not self.env.su:
            raise UserError(_(
                "El consentimiento no se crea en lote: cada uno refleja una autorización "
                "realmente obtenida, con su evidencia."))
        if not self.env.su:
            for vals in vals_list:
                vals["user_id"] = self.env.uid
        return super().create(vals_list)
