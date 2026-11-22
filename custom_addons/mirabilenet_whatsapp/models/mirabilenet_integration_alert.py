from odoo import api, fields, models, _
from odoo.exceptions import AccessError

from .mirabilenet_support_case import OPERATOR


class MirabilenetIntegrationAlert(models.Model):
    """Fallo que informa un flujo de n8n, o la propia integración, para que alguien lo vea."""
    _name = "mirabilenet.integration.alert"
    _description = "MIRABILENET: alerta de integración"
    _order = "state, last_at desc"
    _rec_name = "workflow"

    workflow = fields.Char(string="Flujo", required=True, readonly=True)
    node = fields.Char(string="Nodo", readonly=True)
    message = fields.Char(string="Mensaje de error", required=True, readonly=True)
    execution_id = fields.Char(string="Ejecución en n8n", readonly=True)
    key = fields.Char(string="Clave", required=True, readonly=True, index=True)
    repetitions = fields.Integer(string="Repeticiones", default=1, readonly=True)
    state = fields.Selection([("nueva", "Nueva"), ("resuelta", "Resuelta")], string="Estado",
                             default="nueva", required=True, index=True, readonly=True)
    resolved_by = fields.Many2one("res.users", string="Resuelta por", readonly=True)
    last_at = fields.Datetime(string="Última vez", default=fields.Datetime.now, readonly=True)
    resolved_at = fields.Datetime(string="Resuelta el", readonly=True)

    _key_uniq = models.Constraint("unique(key)", "Alerta repetida.")

    @api.model
    def _raise(self, key, workflow, node, message, execution_id=""):
        """La misma falla repetida suma: no crea otra alerta. Devuelve (alerta, creada)."""
        Alert = self.sudo()
        alert = Alert.search([("key", "=", key)], limit=1)
        if not alert:
            return Alert.create({"key": key, "workflow": workflow, "node": node or False,
                                 "message": message, "execution_id": execution_id or False}), True
        alert.write({"repetitions": alert.repetitions + 1, "last_at": fields.Datetime.now(),
                     "execution_id": execution_id or alert.execution_id, "state": "nueva",
                     "message": message})
        return alert, False

    def action_resolve(self):
        if not self.env.su and not self.env.user.has_group(OPERATOR):
            raise AccessError(_("Su rol no resuelve alertas."))
        self.sudo().write({"state": "resuelta", "resolved_by": self.env.uid,
                           "resolved_at": fields.Datetime.now()})
        return True
