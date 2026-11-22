from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

SERVICE_MANAGER = "mirabilenet_isp.group_mirabilenet_service_manager"
SERVICE_STATES = [
    ("pendiente_instalacion", "Pendiente de instalación"),
    ("activo", "Activo"),
    ("moroso", "Moroso"),
    ("suspendido", "Suspendido"),
    ("baja", "De baja"),
]
#: A qué estado lleva cada acción una vez confirmada en el equipo.
STATE_AFTER = {"suspender": "suspendido", "activar": "activo", "corte_parcial": "moroso",
               "baja": "baja"}
OPEN_TRANSITIONS = ("pendiente", "en_proceso", "reintento")


class MirabilenetService(models.Model):
    """Servicio de internet contratado por un cliente."""
    _name = "mirabilenet.service"
    _description = "MIRABILENET: servicio"
    _inherit = ["mail.thread", "mirabilenet.region.scoped"]
    _order = "id desc"

    name = fields.Char(string="Servicio", compute="_compute_name", store=True)
    partner_id = fields.Many2one(
        "res.partner", string="Cliente", required=True, ondelete="restrict", index=True,
        domain="[('mirabilenet_is_customer', '=', True)]", tracking=True)
    region_id = fields.Many2one("mirabilenet.region", string="Región", required=True,
                                ondelete="restrict", index=True)
    node_id = fields.Many2one("mirabilenet.node", string="Nodo", ondelete="set null",
                              domain="[('region_id', '=', region_id)]")
    router_id = fields.Many2one("mirabilenet.router", string="Router", ondelete="set null",
                                domain="[('region_id', '=', region_id)]")
    plan_id = fields.Many2one(
        "product.template", string="Plan", required=True, ondelete="restrict", tracking=True,
        domain="[('mirabilenet_is_plan', '=', True), '|', "
               "('mirabilenet_region_id', '=', False), "
               "('mirabilenet_region_id', '=', region_id)]")
    state = fields.Selection(
        SERVICE_STATES, string="Estado", default="pendiente_instalacion", required=True,
        readonly=True, index=True, copy=False, tracking=True,
        help="Solo cambia cuando el equipo confirma la orden.")
    payment_mode = fields.Selection(
        [("prepago", "Prepago"), ("pospago", "Pospago")], string="Modalidad de pago",
        default="pospago", required=True, index=True, tracking=True,
        help="Prepago cobra antes del período; pospago cobra el período ya prestado. "
             "Va en el servicio, no en el cliente.")
    date_start = fields.Date(string="Fecha de alta", copy=False)
    date_end = fields.Date(string="Fecha de baja", readonly=True, copy=False)
    billing_day = fields.Integer(
        string="Día de cobro", compute="_compute_billing_day", store=True,
        help="Prepago: el día de emisión prepago de la región, igual para todos sus "
             "servicios. Pospago: el día del alta de este servicio.")
    currency_id = fields.Many2one(related="region_id.currency_id")
    monthly_price = fields.Monetary(
        string="Precio mensual", currency_field="currency_id", tracking=True,
        help="Copia del precio del plan al contratar; permite descuentos.")
    install_address = fields.Char(string="Dirección de instalación")
    notes = fields.Text(string="Observaciones")

    pppoe_ids = fields.One2many("mirabilenet.pppoe.account", "service_id",
                                string="Cuenta PPPoE")
    transition_ids = fields.One2many("mirabilenet.service.transition", "service_id",
                                     string="Órdenes de red")
    pending_transition = fields.Boolean(string="Orden en curso",
                                        compute="_compute_pending_transition")

    @api.depends("partner_id.mirabilenet_code", "plan_id.mirabilenet_plan_code")
    def _compute_name(self):
        for service in self:
            service.name = "%s - %s" % (
                service.partner_id.mirabilenet_code or service.partner_id.name or "",
                service.plan_id.mirabilenet_plan_code or "")

    @api.depends("transition_ids.state")
    def _compute_pending_transition(self):
        for service in self:
            service.pending_transition = any(
                t.state in OPEN_TRANSITIONS for t in service.transition_ids)

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if self.partner_id.mirabilenet_region_id:
            self.region_id = self.partner_id.mirabilenet_region_id
        if not self.install_address:
            self.install_address = self.partner_id.street

    @api.onchange("plan_id")
    def _onchange_plan_id(self):
        if self.plan_id and not self.monthly_price:
            self.monthly_price = self.plan_id.list_price

    @api.depends("payment_mode", "date_start", "region_id.dia_emision_prepago")
    def _compute_billing_day(self):
        for service in self:
            if service.payment_mode == "pospago":
                service.billing_day = service.date_start.day if service.date_start else 1
            else:
                service.billing_day = service.region_id.dia_emision_prepago or 1

    @api.constrains("partner_id", "region_id", "plan_id", "router_id", "node_id",
                    "billing_day", "monthly_price")
    def _check_service(self):
        for service in self:
            region = service.region_id
            partner = service.partner_id.sudo()
            if not partner.mirabilenet_is_customer:
                raise ValidationError(_("El servicio se contrata a nombre de un cliente."))
            if partner.mirabilenet_region_id != region:
                raise ValidationError(_("El servicio va en la región de su cliente."))
            plan = service.plan_id.sudo()
            if not plan.mirabilenet_is_plan:
                raise ValidationError(_("Elija un plan de internet."))
            if plan.mirabilenet_region_id and plan.mirabilenet_region_id != region:
                raise ValidationError(_("Ese plan no vale en la región del servicio."))
            if service.router_id and service.router_id.region_id != region:
                raise ValidationError(_("El router no pertenece a la región del servicio."))
            if service.node_id and service.node_id.region_id != region:
                raise ValidationError(_("El nodo no pertenece a la región del servicio."))
            if not 1 <= service.billing_day <= 31:
                raise ValidationError(_("El día de facturación va de 1 a 31."))
            if service.monthly_price < 0:
                raise ValidationError(_("El precio mensual no puede ser negativo."))

    # ------------------------------------------------------------------
    def _state_allowed(self):
        # Solo el código del sistema. Una bandera de contexto no vale: el contexto lo
        # envía el cliente.
        return self.env.su

    @api.model_create_multi
    def create(self, vals_list):
        Partner = self.env["res.partner"].sudo()
        Plan = self.env["product.template"].sudo()
        for vals in vals_list:
            if not self._state_allowed():
                vals.pop("state", None)
                vals.pop("date_end", None)
            if not vals.get("region_id"):
                vals["region_id"] = Partner.browse(
                    vals.get("partner_id")).mirabilenet_region_id.id
            if "monthly_price" not in vals:
                # Sin precio propio se copia el del plan: no se inventa otro.
                vals["monthly_price"] = Plan.browse(vals.get("plan_id")).list_price
        return super().create(vals_list)

    def write(self, vals):
        if {"state", "date_end"} & set(vals) and not self._state_allowed():
            raise UserError(_(
                "El estado del servicio cambia con sus acciones y solo cuando el equipo "
                "confirma la orden."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise UserError(_("Un servicio no se elimina: se da de baja."))
        return super().unlink()

    # ------------------------------------------------------------------
    # Órdenes de red
    # ------------------------------------------------------------------
    def _require_service_manager(self):
        if not self.env.su and not self.env.user.has_group(SERVICE_MANAGER):
            raise AccessError(_("Su rol no puede dar órdenes sobre servicios."))
        self.check_access("write")

    def _request_transition(self, action, reason="", key="", run=True):
        """Encola una orden de red. Idempotente por clave. Devuelve (orden, creada)."""
        self.ensure_one()
        Transition = self.env["mirabilenet.service.transition"].sudo()
        if key:
            self.env.cr.execute(
                "SELECT id FROM mirabilenet_service WHERE id = %s FOR UPDATE", [self.id])
            existing = Transition.search([("idempotency_key", "=", key)], limit=1)
            if existing:
                return existing, False
        transition = Transition.create({
            "service_id": self.id, "action": action, "reason": reason,
            "user_id": self.env.user.id, "idempotency_key": key or False,
        })
        if run:
            # Nunca dentro de la petición del usuario: lo toma la tarea programada.
            self.env.ref("mirabilenet_isp.cron_process_transitions").sudo()._trigger()
        return transition, True

    def _send_order(self, action, reason):
        self._require_service_manager()
        for service in self:
            if service.state == "baja":
                raise UserError(_("%s está de baja.", service.display_name))
            service._request_transition(action, reason=reason)
        return True

    def action_activate(self):
        return self._send_order("activar", _("Activación solicitada"))

    def action_suspend(self):
        return self._send_order("suspender", _("Suspensión solicitada"))

    def action_partial_cut(self):
        return self._send_order("corte_parcial", _("Corte parcial solicitado"))

    def action_disconnect(self):
        return self._send_order("desconectar", _("Desconexión de la sesión solicitada"))

    def action_change_plan(self, plan):
        """Cambia el plan y pide al equipo aplicar su perfil. El precio no se toca solo."""
        self._require_service_manager()
        for service in self:
            service.plan_id = plan
            if service.pppoe_ids and service.router_id:
                service._request_transition("cambiar_plan", reason=_("Cambio de plan"))
        return True

    def action_terminate(self):
        """Baja. Si hay cuenta en un router, primero se deshabilita allí."""
        self._require_service_manager()
        for service in self.filtered(lambda s: s.state != "baja"):
            if service.pppoe_ids and service.router_id:
                service._request_transition("baja", reason=_("Baja del servicio"))
            else:
                service._apply_confirmed_state("baja")
                self.env["mirabilenet.audit.log"]._log(
                    "servicio_suspender", "Baja de %s sin equipo que desconectar"
                    % service.display_name, record=service, region=service.region_id)
        return True

    def _apply_confirmed_state(self, action):
        """Único lugar donde se mueve el estado del servicio."""
        self.ensure_one()
        new_state = STATE_AFTER.get(action)
        if not new_state:
            return
        vals = {"state": new_state}
        if action == "activar" and not self.date_start:
            vals["date_start"] = fields.Date.context_today(self)
        if action == "baja":
            vals["date_end"] = fields.Date.context_today(self)
        self.sudo().write(vals)

    def _mirabilenet_on_activated(self, transition):
        """Punto de enganche para los cobros: el prorrateo de un alta prepaga."""
        return None
