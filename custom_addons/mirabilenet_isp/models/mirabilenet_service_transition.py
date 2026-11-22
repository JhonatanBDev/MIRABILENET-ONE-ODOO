import logging
import uuid

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..isp.gateway import GatewayError

_logger = logging.getLogger(__name__)

ACTIONS = [
    ("activar", "Activar"),
    ("suspender", "Suspender"),
    ("corte_parcial", "Corte parcial"),
    ("cambiar_plan", "Cambiar plan"),
    ("desconectar", "Desconectar sesión"),
    ("baja", "Dar de baja"),
]


class MirabilenetServiceTransition(models.Model):
    """Orden de red. El servicio no cambia de estado hasta que el equipo la confirma."""
    _name = "mirabilenet.service.transition"
    _description = "MIRABILENET: orden de red de un servicio"
    _order = "id desc"
    _rec_name = "action"

    uuid = fields.Char(string="Identificador", default=lambda self: str(uuid.uuid4()),
                       readonly=True, copy=False, index=True)
    service_id = fields.Many2one("mirabilenet.service", string="Servicio", required=True,
                                 ondelete="cascade", index=True, readonly=True)
    region_id = fields.Many2one(related="service_id.region_id", store=True, index=True)
    action = fields.Selection(ACTIONS, string="Acción", required=True, readonly=True)
    state = fields.Selection(
        [("pendiente", "Pendiente"), ("en_proceso", "En proceso"),
         ("confirmada", "Confirmada"), ("reintento", "Reintento"),
         ("revision_manual", "Revisión manual"), ("cancelada", "Cancelada")],
        string="Estado", default="pendiente", required=True, readonly=True, index=True)
    reason = fields.Char(string="Motivo", readonly=True)
    attempts = fields.Integer(string="Intentos", readonly=True)
    max_attempts = fields.Integer(string="Máximo de intentos", default=3, readonly=True)
    error_detail = fields.Text(string="Detalle del error", readonly=True)
    summary = fields.Char(string="Resultado", readonly=True)
    started_at = fields.Datetime(string="Iniciada", readonly=True)
    confirmed_at = fields.Datetime(string="Confirmada el", readonly=True)
    user_id = fields.Many2one("res.users", string="Solicitada por", readonly=True)
    idempotency_key = fields.Char(string="Clave de idempotencia", readonly=True, index=True)

    _key_uniq = models.Constraint(
        "unique(idempotency_key)", "Esa orden ya fue solicitada.")

    def write(self, vals):
        if not self.env.su:
            raise UserError(_("Las órdenes de red no se editan."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise UserError(_("Las órdenes de red no se eliminan."))
        return super().unlink()

    # ------------------------------------------------------------------
    def _apply_in_router(self):
        """Ejecuta la acción en el equipo. Lanza GatewayError si no se puede."""
        self.ensure_one()
        service = self.service_id
        account = service.pppoe_ids[:1]
        router = service.router_id
        if not account:
            raise GatewayError("El servicio no tiene cuenta PPPoE.")
        if not router:
            raise GatewayError("El servicio no tiene router asignado.")
        if router.state not in ("conectado", "degradado"):
            raise GatewayError("El router %s está %s." % (
                router.name, dict(router._fields["state"].selection)[router.state]))
        if not router.api_password_enc:
            raise GatewayError(
                "El router %s no tiene credenciales de servicio." % router.name)
        plan = service.plan_id
        result = router._gateway().apply(
            router._target(), self.action, account.username,
            profile=plan.mirabilenet_profile_name,
            reduced_profile=plan.mirabilenet_reduced_profile or plan.mirabilenet_profile_name)
        account.write({"enabled": result["enabled"], "profile": result["profile"],
                       "synced": result["synced"]})
        return result["summary"]

    def _confirm(self, summary):
        self.ensure_one()
        service = self.service_id
        service._apply_confirmed_state(self.action)
        self.write({"state": "confirmada", "confirmed_at": fields.Datetime.now(),
                    "error_detail": False, "summary": summary})
        if self.action == "activar":
            service._mirabilenet_on_activated(self)
        self.env["mirabilenet.audit.log"].with_user(self.user_id or self.env.user)._log(
            "servicio_suspender" if self.action in ("suspender", "corte_parcial", "baja")
            else "servicio_activar",
            "%s confirmada: %s" % (dict(ACTIONS)[self.action], summary),
            record=service, region=service.region_id,
            payload={"orden": self.uuid, "motivo": self.reason})

    def _fail(self, error):
        self.ensure_one()
        attempts = self.attempts + 1
        manual = attempts >= self.max_attempts
        self.write({"attempts": attempts, "error_detail": (error or "")[:2000],
                    "state": "revision_manual" if manual else "reintento"})
        if manual:
            _logger.error("Orden %s a revisión manual tras %s intentos: %s",
                          self.uuid, attempts, error)

    def _execute(self):
        """Procesa cada orden por separado: el fallo de una no arrastra a las demás."""
        for transition in self.sudo():
            if transition.state not in ("pendiente", "reintento"):
                continue
            transition.write({"state": "en_proceso", "started_at": fields.Datetime.now()})
            try:
                with self.env.cr.savepoint():
                    summary = transition._apply_in_router()
            except GatewayError as exc:
                transition._fail(str(exc))
                continue
            transition._confirm(summary)
        return True

    @api.model
    def _cron_process(self):
        self.sudo().search([("state", "in", ("pendiente", "reintento"))], order="id")._execute()

    def action_retry(self):
        """Devuelve a la cola una orden que quedó en revisión manual."""
        self.service_id._require_service_manager()
        for transition in self.sudo().filtered(lambda t: t.state == "revision_manual"):
            transition.write({"state": "pendiente", "attempts": 0})
        self.env.ref("mirabilenet_isp.cron_process_transitions").sudo()._trigger()
        return True

    def action_cancel(self):
        self.service_id._require_service_manager()
        self.sudo().filtered(
            lambda t: t.state in ("pendiente", "reintento", "revision_manual")
        ).write({"state": "cancelada"})
        return True
