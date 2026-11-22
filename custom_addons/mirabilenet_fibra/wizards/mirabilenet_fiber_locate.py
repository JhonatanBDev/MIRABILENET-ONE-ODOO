import re

from markupsafe import Markup, escape

from odoo import _, api, fields, models

IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
#: Con este número de averías abiertas en una misma caja, la sospecha pasa a la caja.
BOX_FAILURE_THRESHOLD = 2


class MirabilenetFiberLocate(models.TransientModel):
    """Del cliente con problemas a su caja NAP: dónde está, cómo llegar y qué le pasa a sus
    vecinos, para decidir si se revisa la caja, el tramo o el equipo del cliente."""
    _name = "mirabilenet.fiber.locate"
    _description = "MIRABILENET: ubicar cliente en la red de fibra"

    query = fields.Char(string="IP, usuario PPPoE, nombre o C.I.", required=True)
    service_id = fields.Many2one("mirabilenet.service", string="Servicio", readonly=True)
    partner_id = fields.Many2one(related="service_id.partner_id", string="Cliente")
    nap_id = fields.Many2one("mirabilenet.fiber.nap", string="Caja NAP", readonly=True)
    port_id = fields.Many2one("mirabilenet.fiber.port", string="Puerto", readonly=True)
    maps_url = fields.Char(related="nap_id.maps_url")
    result = fields.Html(string="Resultado", readonly=True, sanitize=True)
    searched = fields.Boolean(readonly=True)

    # ------------------------------------------------------------------
    def _find_services(self, query):
        """Servicios que el usuario puede ver y que coinciden con la búsqueda (sus reglas de
        región aplican: no se usa sudo)."""
        Service = self.env["mirabilenet.service"]
        Pppoe = self.env["mirabilenet.pppoe.account"]
        if IP_RE.match(query):
            accounts = Pppoe.search(["|", ("fixed_ip", "=", query), ("last_ip", "=", query)])
            return accounts.mapped("service_id")
        accounts = Pppoe.search([("username", "=ilike", query)])
        if accounts:
            return accounts.mapped("service_id")
        partners = self.env["res.partner"].search([
            ("mirabilenet_is_customer", "=", True), "|", "|", "|",
            ("name", "ilike", query), ("vat", "=", query), ("phone", "ilike", query),
            ("mirabilenet_code", "=ilike", query)], limit=20)
        services = Service.search([("partner_id", "in", partners.ids)])
        return services | Pppoe.search([("username", "ilike", query)], limit=20).mapped(
            "service_id")

    def action_search(self):
        self.ensure_one()
        query = (self.query or "").strip()
        services = self._find_services(query) if query else self.env["mirabilenet.service"]
        services = services.sorted(lambda s: (s.state == "baja", s.id))
        service = services[:1]
        port = service.fiber_port_id
        self.write({"service_id": service.id, "port_id": port.id,
                    "nap_id": port.nap_id.id, "searched": True,
                    "result": self._render(query, service, port, services - service)})
        return self._reopen()

    # ------------------------------------------------------------------
    def _open_failures(self, domain):
        return self.env["maintenance.request"].sudo().search_count(
            domain + [("stage_id.done", "=", False), ("archive", "=", False)])

    def _render(self, query, service, port, others):
        if not service:
            return Markup("<p class='text-danger'>%s</p>") % _(
                "No se encontró ningún cliente con «%s» en su región.", query)
        html = Markup()
        partner = service.partner_id
        account = service.pppoe_ids[:1]
        html += Markup("<h4>%s</h4><ul>") % partner.display_name
        rows = [
            (_("Servicio"), "%s · %s" % (service.plan_id.name or "",
                                        dict(service._fields["state"].selection).get(
                                            service.state, ""))),
            (_("IP"), account.fixed_ip or _("sin IP fija")),
            (_("Usuario PPPoE"), account.username or "-"),
            (_("Teléfono"), partner.phone or partner.mirabilenet_whatsapp or "-"),
            (_("Dirección del cliente"), service.install_address or partner.street or "-"),
        ]
        html += Markup("").join(Markup("<li><b>%s:</b> %s</li>") % row for row in rows)
        html += Markup("</ul>")
        if not port:
            html += Markup("<p class='text-warning'>%s</p>") % _(
                "Este servicio no tiene caja NAP asignada. Asígnele un puerto desde el "
                "servicio para poder ubicarlo en la red.")
            return html + self._render_others(others)

        nap = port.nap_id
        html += Markup("<h4>%s</h4><ul>") % _("Caja %(nap)s · Puerto %(port)s",
                                               nap=nap.display_name, port=port.number)
        rows = [
            (_("Dirección o referencia"), nap.address_reference or _("sin referencia")),
            (_("Zona o barrio"), nap.neighborhood or "-"),
            (_("Ramal"), nap.branch_line or "-"),
            (_("OLT / puerto PON"), "%s / %s" % (nap.olt or "-", nap.pon_port or "-")),
            (_("Coordenadas"), "%s, %s" % (nap.latitude, nap.longitude)
             if nap.latitude and nap.longitude else _("sin coordenadas")),
        ]
        html += Markup("").join(Markup("<li><b>%s:</b> %s</li>") % row for row in rows)
        html += Markup("</ul>")
        if nap.maps_url:
            html += Markup("<p><a href='%s' target='_blank' rel='noopener'>%s</a></p>") % (
                nap.maps_url, _("Cómo llegar (Google Maps)"))
        if nap.needs_review:
            html += Markup("<p class='text-warning'>%s %s</p>") % (
                _("Caja marcada «revisar en campo»:"), nap.review_note or "")

        # Diagnóstico: ¿le pasa solo a este cliente o a varios de la misma caja?
        in_box = self._open_failures([("mirabilenet_fiber_nap_id", "=", nap.id)])
        if in_box >= BOX_FAILURE_THRESHOLD:
            hint = _("Hay %s averías abiertas en esta caja: revise primero la caja y el tramo "
                     "que la alimenta.", in_box)
            css = "text-danger"
        elif in_box == 1:
            hint = _("Hay 1 avería abierta en esta caja. Si a los vecinos les funciona, "
                     "probablemente es el equipo o el cable del cliente (ONU, drop, router).")
            css = "text-muted"
        else:
            hint = _("No hay otras averías abiertas en esta caja: probablemente es el equipo o "
                     "el cable del cliente (ONU, drop, router).")
            css = "text-muted"
        html += Markup("<p class='%s'><b>%s</b></p>") % (css, hint)

        html += Markup("<table class='table table-sm'><thead><tr><th>%s</th><th>%s</th>"
                       "<th>%s</th><th>%s</th><th>%s</th></tr></thead><tbody>") % (
            _("Puerto"), _("Estado"), _("Cliente"), _("IP"), _("Averías abiertas"))
        states = dict(port._fields["state"].selection)
        for p in nap.port_ids.sorted("number"):
            failures = self._open_failures([("mirabilenet_service_id", "=", p.service_id.id)]) \
                if p.service_id else 0
            style = Markup(" class='table-info'") if p == port else Markup("")
            html += Markup("<tr%s><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                           "</tr>") % (style, p.number, states.get(p.state, ""),
                                       p.partner_id.display_name or "-", p.service_ip or "-",
                                       failures or "")
        html += Markup("</tbody></table>")
        segments = nap.stop_ids.mapped("segment_id")
        if segments:
            html += Markup("<p><b>%s</b> %s</p>") % (
                _("Tramos que pasan por la caja:"),
                ", ".join(segments.mapped("display_name")))
        return html + self._render_others(others)

    def _render_others(self, others):
        if not others:
            return Markup()
        items = Markup("").join(
            Markup("<li>%s · %s · %s</li>") % (
                s.partner_id.display_name, s.pppoe_ids[:1].fixed_ip or "-",
                s.fiber_nap_id.display_name or _("sin caja")) for s in others[:10])
        return Markup("<p><b>%s</b></p><ul>%s</ul>") % (
            _("También coinciden (escriba la IP o el usuario PPPoE para elegir):"), items)

    # ------------------------------------------------------------------
    def action_open_map(self):
        self.ensure_one()
        return self.nap_id.action_open_map()

    def action_open_nap(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "mirabilenet.fiber.nap",
                "res_id": self.nap_id.id, "view_mode": "form", "target": "current"}

    def action_new_failure(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "maintenance.request",
                "view_mode": "form", "target": "current", "name": _("Nueva avería"),
                "context": {"default_mirabilenet_service_id": self.service_id.id,
                            "default_mirabilenet_fiber_nap_id": self.nap_id.id,
                            "default_mirabilenet_fiber_port_id": self.port_id.id,
                            "default_name": _("Sin servicio: %s",
                                              self.service_id.partner_id.display_name)}}

    def _reopen(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
                "view_mode": "form", "target": "new", "name": _("Ubicar cliente")}

    @api.model
    def action_open_from_service(self, service):
        """Abre el asistente ya resuelto para un servicio (botón en el servicio y la avería)."""
        account = service.pppoe_ids[:1]
        wizard = self.create({"query": account.fixed_ip or account.username
                              or service.partner_id.name})
        return wizard.action_search()
