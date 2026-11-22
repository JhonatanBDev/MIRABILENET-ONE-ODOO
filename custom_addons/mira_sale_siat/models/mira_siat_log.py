from odoo import fields, models, _
from odoo.exceptions import UserError


class MiraSiatLog(models.Model):
    """Evidencia técnica de cada intercambio con el SIN (sin token, con
    CUIS/CUFD enmascarados y sin el archivo binario)."""
    _name = "mira.siat.log"
    _description = "Mira_Sale SIAT: intercambio técnico"
    _order = "id desc"
    _rec_name = "operation"

    company_id = fields.Many2one("res.company", string="Empresa", index=True, readonly=True)
    user_id = fields.Many2one("res.users", string="Usuario", readonly=True)
    service = fields.Char(string="Servicio", readonly=True)
    operation = fields.Char(string="Operación", readonly=True, index=True)
    request_xml = fields.Text(string="Solicitud", readonly=True)
    response_xml = fields.Text(string="Respuesta", readonly=True)
    duration_ms = fields.Integer(string="Duración (ms)", readonly=True)
    success = fields.Boolean(string="Comunicación correcta", readonly=True)
    error_code = fields.Char(string="Código de error", readonly=True)
    correlation_id = fields.Char(string="Correlación", readonly=True, index=True)

    def write(self, vals):
        raise UserError(_("La evidencia técnica no se puede modificar."))

    def unlink(self):
        raise UserError(_("La evidencia técnica no se puede eliminar."))
