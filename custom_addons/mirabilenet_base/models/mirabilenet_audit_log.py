from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MirabilenetAuditLog(models.Model):
    """Registro inmutable de acciones críticas: quién, cuándo y qué cambió."""
    _name = "mirabilenet.audit.log"
    _description = "MIRABILENET: registro de auditoría"
    _order = "id desc"
    _rec_name = "description"

    user_id = fields.Many2one("res.users", string="Quién", readonly=True, index=True)
    action = fields.Char(string="Acción", required=True, readonly=True, index=True)
    model = fields.Char(string="Entidad", readonly=True, index=True)
    res_id = fields.Integer(string="Id de la entidad", readonly=True)
    region_id = fields.Many2one("mirabilenet.region", string="Región", readonly=True, index=True)
    description = fields.Char(string="Descripción", readonly=True)
    payload = fields.Json(string="Datos", readonly=True)

    def write(self, vals):
        raise UserError(_("Los registros de auditoría no se modifican."))

    def unlink(self):
        raise UserError(_("Los registros de auditoría no se eliminan."))

    @api.model
    def _log(self, action, description, record=None, region=None, payload=None):
        """Deja una entrada. El actor es el usuario real, también bajo sudo."""
        return self.sudo().create({
            "user_id": self.env.user.id,
            "action": action,
            "model": record._name if record else False,
            "res_id": record.id if record else False,
            "region_id": region.id if region else False,
            "description": description,
            "payload": payload or {},
        })
