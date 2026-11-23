"""Averías de clientes: se asignan solas al técnico de la zona, le llegan por WhatsApp con los
datos de la caja NAP y él las cierra desde WhatsApp."""
import logging
from datetime import timedelta

from odoo import _, api, fields, models

from .res_users import FIELD_ROLES

_logger = logging.getLogger(__name__)

DISPATCH_STATES = [
    ("sin_asignar", "Sin técnico"),
    ("avisado", "Técnico avisado"),
    ("en_camino", "En camino"),
    ("arreglado", "Arreglado"),
    ("no_resuelto", "No se pudo arreglar"),
]
#: Horas sin respuesta antes de recordarle al técnico (y avisar al jefe), y horas abiertas
#: antes de avisar al jefe aunque el técnico ya haya dicho que va.
ACCEPT_HOURS_PARAM = "mirabilenet.personal_horas_aceptar"
CLOSE_HOURS_PARAM = "mirabilenet.personal_horas_cerrar"


class MaintenanceRequest(models.Model):
    _inherit = "maintenance.request"

    mirabilenet_dispatch_state = fields.Selection(
        DISPATCH_STATES, string="Atención en campo", default="sin_asignar", index=True,
        tracking=True, copy=False)
    mirabilenet_assigned_at = fields.Datetime(string="Técnico avisado el", copy=False)
    mirabilenet_accepted_at = fields.Datetime(string="En camino desde", copy=False)
    mirabilenet_closed_at = fields.Datetime(string="Cerrada por el técnico", copy=False)
    mirabilenet_result_note = fields.Text(string="Nota del técnico", copy=False)
    mirabilenet_reminded = fields.Boolean(string="Recordado al técnico", copy=False)
    mirabilenet_supervisor_alerted = fields.Boolean(string="Jefe avisado", copy=False)
    mirabilenet_notice_ids = fields.One2many("mirabilenet.staff.notice", "request_id",
                                             string="Avisos por WhatsApp")

    # ------------------------------------------------------------------
    # Asignar y avisar
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        requests = super().create(vals_list)
        for request in requests.filtered(
                lambda r: r.mirabilenet_service_id and not r.stage_id.done):
            if not request.user_id:
                technician = request._mirabilenet_pick_technician()
                if technician:
                    request.with_context(mirabilenet_no_notify=True).user_id = technician
            if request.user_id:
                request._mirabilenet_notify_assigned()
        return requests

    def write(self, vals):
        before = {r.id: r.user_id for r in self} if "user_id" in vals else {}
        result = super().write(vals)
        if before and not self.env.context.get("mirabilenet_no_notify"):
            for request in self.filtered(
                    lambda r: r.mirabilenet_service_id and not r.stage_id.done and r.user_id):
                if request.user_id != before.get(request.id):
                    request._mirabilenet_notify_assigned()
        return result

    def _mirabilenet_zone(self):
        self.ensure_one()
        return self.mirabilenet_service_id.node_id.zone_id

    def _mirabilenet_pick_technician(self):
        """El técnico de la zona con menos averías abiertas; si nadie atiende la zona, el de
        la región que menos tenga; si no hay técnicos, el encargado de la región."""
        self.ensure_one()
        service = self.mirabilenet_service_id
        Users = self.env["res.users"].sudo()
        technicians = Users.search([("mirabilenet_role", "in", FIELD_ROLES),
                                    ("mirabilenet_region_id", "=", service.region_id.id)])
        technicians = technicians._mirabilenet_reachable()
        zone = self._mirabilenet_zone()
        in_zone = technicians.filtered(lambda u: zone in u.mirabilenet_zone_ids) if zone else \
            technicians.browse()
        candidates = in_zone or technicians.filtered(lambda u: not u.mirabilenet_zone_ids) \
            or technicians
        if not candidates:
            return Users._mirabilenet_region_supervisors(service.region_id)[:1]
        load = {u.id: self.sudo().search_count([("user_id", "=", u.id),
                                                ("stage_id.done", "=", False)])
                for u in candidates}
        return candidates.sorted(lambda u: (load[u.id], u.id))[:1]

    def _mirabilenet_notify_assigned(self):
        for request in self:
            request.sudo().with_context(mirabilenet_no_notify=True).write({
                "mirabilenet_dispatch_state": "avisado",
                "mirabilenet_assigned_at": fields.Datetime.now(),
                "mirabilenet_reminded": False, "mirabilenet_supervisor_alerted": False})
            self.env["mirabilenet.staff.notice"]._notify(
                request.user_id, "averia_asignada", request._mirabilenet_staff_values(),
                request=request)
            request.message_post(body=_("Se avisó por WhatsApp a %s.", request.user_id.name))

    # ------------------------------------------------------------------
    # Datos del aviso
    # ------------------------------------------------------------------
    def _mirabilenet_ref(self):
        self.ensure_one()
        return "AV-%s" % self.id

    def _mirabilenet_label(self):
        self.ensure_one()
        nap = self.mirabilenet_fiber_nap_id
        parts = [self._mirabilenet_ref(), self.mirabilenet_partner_id.name or self.name]
        if nap:
            parts.append(_("caja %s", nap.code))
        return " · ".join(p for p in parts if p)

    def _mirabilenet_open_in_box(self):
        self.ensure_one()
        nap = self.mirabilenet_fiber_nap_id
        if not nap:
            return 0
        return self.sudo().search_count([("mirabilenet_fiber_nap_id", "=", nap.id),
                                         ("stage_id.done", "=", False), ("id", "!=", self.id)])

    def _mirabilenet_open_in_zone(self):
        self.ensure_one()
        zone = self._mirabilenet_zone()
        domain = [("stage_id.done", "=", False), ("id", "!=", self.id),
                  ("mirabilenet_service_id", "!=", False)]
        if zone:
            domain.append(("mirabilenet_service_id.node_id.zone_id", "=", zone.id))
        else:
            domain.append(("mirabilenet_service_id.region_id", "=",
                           self.mirabilenet_service_id.region_id.id))
        return self.sudo().search_count(domain)

    def _mirabilenet_staff_values(self):
        """Lo que necesita el técnico para ir a la caja, con las mismas pistas que «Ubicar
        cliente»: si a varios de la caja les falla, el problema está en la caja."""
        self.ensure_one()
        service = self.mirabilenet_service_id
        partner = service.partner_id
        nap = self.mirabilenet_fiber_nap_id or service.fiber_nap_id
        port = self.mirabilenet_fiber_port_id or service.fiber_port_id
        others = self._mirabilenet_open_in_box()
        if not nap:
            diagnosis = _("Servicio sin caja NAP asignada.")
        elif others >= 1:
            diagnosis = _("Hay %s avería(s) más en esta caja: revise primero la caja y el tramo.",
                          others)
        else:
            diagnosis = _("Ningún vecino de la caja tiene falla: probablemente es el equipo o "
                          "el cable del cliente.")
        return {
            "referencia": self._mirabilenet_ref(),
            "tecnico": self.user_id.name or "",
            "cliente": partner.name or "",
            "telefono": partner.mirabilenet_whatsapp or partner.phone or "",
            "direccion": service.install_address or partner.street or "",
            "caja": ("%s %s" % (nap.code, nap.address_reference or "")).strip() if nap else "",
            "puerto": str(port.number) if port else "",
            "vecinos": diagnosis,
            "mapa": nap.maps_url if nap else "",
        }

    def _mirabilenet_brief(self):
        """Resumen para n8n."""
        self.ensure_one()
        values = self._mirabilenet_staff_values()
        return {"id": self.id, "referencia": values["referencia"], "cliente": values["cliente"],
                "caja": values["caja"], "estado": self.mirabilenet_dispatch_state}

    # ------------------------------------------------------------------
    # Lo que responde el técnico
    # ------------------------------------------------------------------
    def _mirabilenet_stage(self, done):
        Stage = self.env["maintenance.stage"].sudo()
        if done:
            repaired = self.env.ref("maintenance.stage_3", raise_if_not_found=False)
            return repaired if repaired and repaired.done else Stage.search(
                [("done", "=", True)], order="sequence", limit=1)
        current = self.stage_id
        later = Stage.search([("done", "=", False), ("sequence", ">", current.sequence)],
                             order="sequence", limit=1)
        return later or current

    def _mirabilenet_apply_action(self, action, user, note=False):
        """Aplica «en_camino», «arreglado» o «no_resuelto». Devuelve lo que hizo."""
        self.ensure_one()
        request = self.sudo().with_context(mirabilenet_no_notify=True)
        Notice = self.env["mirabilenet.staff.notice"]
        if request.stage_id.done:
            Notice._reply(user, _("La avería %s ya estaba cerrada.", request._mirabilenet_ref()),
                          request)
            return "ya_cerrada"
        now = fields.Datetime.now()
        if action == "en_camino":
            request.write({"mirabilenet_dispatch_state": "en_camino",
                           "mirabilenet_accepted_at": now,
                           "stage_id": request._mirabilenet_stage(done=False).id})
            request.message_post(body=_("%s va en camino (WhatsApp).", user.name))
            Notice._reply(user, _("Anotado: va en camino a %s. Cuando termine, apriete "
                                  "«Arreglado» o «No se pudo».", request._mirabilenet_label()),
                          request)
            return "en_camino"
        if action == "arreglado":
            request.write({"mirabilenet_dispatch_state": "arreglado",
                           "mirabilenet_closed_at": now,
                           "mirabilenet_result_note": note or False,
                           "stage_id": request._mirabilenet_stage(done=True).id})
            request.message_post(body=_("%(u)s marcó la avería como arreglada por WhatsApp.%(n)s",
                                        u=user.name, n=(" " + note) if note else ""))
            request._mirabilenet_after_fixed(user)
            pending = len(Notice._open_assignments(user))
            Notice._reply(user, _("¡Gracias! %(r)s quedó cerrada. Le quedan %(n)s avería(s) "
                                  "abiertas.", r=request._mirabilenet_ref(), n=pending), request)
            return "arreglado"
        if action == "no_resuelto":
            request.write({"mirabilenet_dispatch_state": "no_resuelto",
                           "mirabilenet_result_note": note or False})
            request.message_post(body=_("%(u)s no pudo arreglarla: %(n)s", u=user.name,
                                        n=note or "-"))
            supervisors = user._mirabilenet_supervisors()
            values = dict(request._mirabilenet_staff_values(), tecnico=user.name, nota=note or "-")
            Notice._notify(supervisors, "averia_no_resuelta", values, request=request)
            Notice._reply(user, _("Anotado. Se avisó a %s.",
                                  ", ".join(supervisors.mapped("name")) or _("la oficina")),
                          request)
            return "no_resuelto"
        return "desconocido"

    def _mirabilenet_after_fixed(self, user):
        """Al cliente, que quedó reparado; a los demás técnicos, que ya no hay que ir."""
        self.ensure_one()
        partner = self.mirabilenet_service_id.partner_id
        try:
            self.env["mirabilenet.whatsapp.message"]._enqueue(
                "servicio_reparado", partner=partner, extra_key=self._mirabilenet_ref())
        except Exception:  # noqa: BLE001 - un aviso al cliente no frena el cierre
            _logger.exception("No se pudo avisar al cliente de la avería %s", self.id)
        zone = self._mirabilenet_zone()
        Users = self.env["res.users"].sudo()
        colleagues = Users.search([("mirabilenet_role", "in", FIELD_ROLES),
                                   ("mirabilenet_region_id", "=",
                                    self.mirabilenet_service_id.region_id.id)])
        if zone:
            in_zone = colleagues.filtered(lambda u: zone in u.mirabilenet_zone_ids)
            colleagues = in_zone or colleagues
        colleagues = (colleagues - user)._mirabilenet_reachable()
        if colleagues:
            values = dict(self._mirabilenet_staff_values(), tecnico=user.name,
                          pendientes_caja=str(self._mirabilenet_open_in_box()),
                          pendientes_zona=str(self._mirabilenet_open_in_zone()))
            self.env["mirabilenet.staff.notice"]._notify(colleagues, "averia_resuelta", values,
                                                         request=self)

    # ------------------------------------------------------------------
    # Recordatorios
    # ------------------------------------------------------------------
    @api.model
    def _cron_mirabilenet_reminders(self):
        Param = self.env["ir.config_parameter"].sudo()
        accept_hours = float(Param.get_param(ACCEPT_HOURS_PARAM, "1") or 1)
        close_hours = float(Param.get_param(CLOSE_HOURS_PARAM, "8") or 8)
        now = fields.Datetime.now()
        Notice = self.env["mirabilenet.staff.notice"]
        late = self.sudo().search([
            ("mirabilenet_dispatch_state", "=", "avisado"), ("mirabilenet_reminded", "=", False),
            ("stage_id.done", "=", False),
            ("mirabilenet_assigned_at", "<=", now - timedelta(hours=accept_hours))])
        for request in late:
            hours = str(int(accept_hours))
            values = dict(request._mirabilenet_staff_values(), horas=hours)
            Notice._notify(request.user_id, "averia_recordatorio", values, request=request)
            Notice._notify(request.user_id._mirabilenet_supervisors(), "averia_sin_atender",
                           values, request=request)
            request.with_context(mirabilenet_no_notify=True).write(
                {"mirabilenet_reminded": True, "mirabilenet_supervisor_alerted": True})
        stuck = self.sudo().search([
            ("mirabilenet_dispatch_state", "in", ("avisado", "en_camino", "no_resuelto")),
            ("mirabilenet_supervisor_alerted", "=", False), ("stage_id.done", "=", False),
            ("mirabilenet_assigned_at", "<=", now - timedelta(hours=close_hours))])
        for request in stuck:
            values = dict(request._mirabilenet_staff_values(), horas=str(int(close_hours)))
            Notice._notify(request.user_id._mirabilenet_supervisors(), "averia_sin_atender",
                           values, request=request)
            request.with_context(mirabilenet_no_notify=True).mirabilenet_supervisor_alerted = True
        return len(late) + len(stuck)

    def action_mirabilenet_notify_again(self):
        """Volver a mandar el aviso al técnico (por ejemplo, si cambió su WhatsApp)."""
        self.filtered("user_id")._mirabilenet_notify_assigned()
        return True
