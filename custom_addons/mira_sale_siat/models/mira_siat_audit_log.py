import json

from odoo import fields, models, _
from odoo.exceptions import UserError


class MiraSiatAuditLog(models.Model):
    """Auditoría append-only de acciones sensibles."""
    _name = "mira.siat.audit.log"
    _description = "Mira_Sale SIAT: auditoría"
    _order = "id desc"
    _rec_name = "action"

    company_id = fields.Many2one("res.company", string="Empresa", index=True, readonly=True)
    user_id = fields.Many2one("res.users", string="Usuario", readonly=True)
    action = fields.Char(string="Acción", required=True, readonly=True, index=True)
    res_model = fields.Char(string="Entidad", readonly=True)
    res_id = fields.Integer(string="ID de la entidad", readonly=True)
    before_json = fields.Json(string="Antes", readonly=True)
    after_json = fields.Json(string="Después", readonly=True)
    ip = fields.Char(string="IP", readonly=True)
    correlation_id = fields.Char(string="Correlación", readonly=True, index=True)
    changes_text = fields.Text(string="Detalle", compute="_compute_changes_text")

    def _compute_changes_text(self):
        for log in self:
            parts = []
            if log.before_json:
                parts.append("Antes: %s" % json.dumps(
                    log.before_json, ensure_ascii=False, indent=2, default=str))
            if log.after_json:
                parts.append("Después: %s" % json.dumps(
                    log.after_json, ensure_ascii=False, indent=2, default=str))
            log.changes_text = "\n".join(parts) or False

    def write(self, vals):
        raise UserError(_("La auditoría no se puede modificar."))

    def unlink(self):
        raise UserError(_("La auditoría no se puede eliminar."))
