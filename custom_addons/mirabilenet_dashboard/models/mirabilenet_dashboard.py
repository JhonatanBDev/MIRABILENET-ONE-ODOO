"""Los números del dashboard. Todo se lee con los permisos del usuario (sin sudo): cada uno ve
solo su región, y los usuarios globales pueden elegir una región o ver todas.

Regla de los indicadores de MIRABILENET: lo que no tiene datos va como None (la pantalla
muestra «—» con su aviso), nunca como 0.

Filtros: un dict con period (hoy, 7, 30, 90, mes, mes_anterior, rango), date_from, date_to,
region_id, zone_id, node_id, plan_id, payment_mode y service_state. Los mismos filtros arman el
número de cada tarjeta y la lista que abre (`action_open`), así siempre coinciden.
"""
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tablero import negocio, periodos

PAYMENT_STATES = ("in_process", "paid")
OPEN_SERVICE_STATES = ("activo", "suspendido", "moroso")
BILLING_STATES = ("activo", "moroso")
#: Cómo se agrupan los estados del cliente en las tarjetas.
CUSTOMER_GROUPS = {
    "prospectos": ("prospecto", "evaluacion", "cotizado"),
    "instalacion": ("instalacion_pendiente",),
    "activos": ("activo", "reactivado"),
    "morosos": ("moroso",),
    "suspendidos": ("suspendido",),
    "bajas": ("baja_solicitada", "cancelado"),
}
ACTIVITY_LIMIT = 8
LAST_PAYMENTS_LIMIT = 8
OVERDUE_LIMIT = 6
TOP_LIMIT = 5
#: Campo de región de cada modelo.
REGION_FIELDS = {
    "mirabilenet.service": "region_id",
    "res.partner": "mirabilenet_region_id",
    "account.payment": "mirabilenet_region_id",
    "account.move": "mirabilenet_region_id",
    "mirabilenet.whatsapp.proof": "region_id",
    "mirabilenet.support.case": "region_id",
    "mirabilenet.router": "region_id",
    "mirabilenet.pppoe.account": "region_id",
    "mirabilenet.node": "region_id",
    "mirabilenet.zone": "region_id",
    "mirabilenet.branch": "region_id",
    "mirabilenet.audit.log": "region_id",
    "pos.config": "mirabilenet_region_id",
    "maintenance.request": "mirabilenet_service_id.region_id",
    "mirabilenet.fiber.port": "nap_id.region_id",
    "mirabilenet.fiber.nap": "region_id",
    "product.template": "mirabilenet_region_id",
    "mirabilenet.region": "id",
}
#: Desde cada modelo, el camino hasta el servicio: por ahí se aplican los filtros de zona, nodo,
#: plan, modalidad y estado. Un modelo que no está aquí no se filtra por esos campos.
SERVICE_PATHS = {
    "mirabilenet.service": "",
    "account.move": "mirabilenet_service_id.",
    "mirabilenet.pppoe.account": "service_id.",
    "maintenance.request": "mirabilenet_service_id.",
    "res.partner": "mirabilenet_service_ids.",
    "account.payment": "partner_id.mirabilenet_service_ids.",
    "mirabilenet.whatsapp.proof": "partner_id.mirabilenet_service_ids.",
    "mirabilenet.support.case": "partner_id.mirabilenet_service_ids.",
}
#: Filtro → (clave en los filtros limpios, campo del servicio).
SERVICE_FILTERS = (
    ("zone", "node_id.zone_id"),
    ("node", "node_id"),
    ("plan", "plan_id"),
    ("payment_mode", "payment_mode"),
    ("service_state", "state"),
)
#: Orden de las secciones según el rol. Lo que el rol no lista va al final.
SECTIONS = ("alertas", "resumen", "negocio", "flujo", "inicio", "cobranza", "operacion",
            "cartera", "capacidad")
ROLE_LAYOUTS = {
    "finanzas": ("alertas", "resumen", "negocio", "cartera", "cobranza", "flujo", "operacion"),
    "cajero": ("alertas", "resumen", "cobranza", "cartera", "operacion"),
    "cobrador": ("alertas", "cartera", "cobranza", "resumen", "operacion"),
    "noc": ("alertas", "operacion", "capacidad", "resumen", "inicio"),
    "tecnico": ("alertas", "operacion", "capacidad", "inicio", "resumen"),
    "vendedor": ("resumen", "negocio", "operacion", "capacidad"),
}
PREF_FILTERS = ("period", "date_from", "date_to", "region_id", "zone_id", "node_id", "plan_id",
                "payment_mode", "service_state")


class MirabilenetDashboard(models.AbstractModel):
    _name = "mirabilenet.dashboard"
    _description = "Dashboard de MIRABILENET"

    # -- Filtros ------------------------------------------------------------------
    @api.model
    def _mirabilenet_record(self, model, value):
        """Un registro elegido en un filtro, solo si existe y el usuario lo puede leer."""
        empty = self.env[model]
        if not value:
            return empty
        try:
            record = empty.browse(int(value)).exists()
        except (TypeError, ValueError):
            return empty
        return record if record and record.has_access("read") else empty

    @api.model
    def _mirabilenet_filters(self, raw):
        """Limpia lo que manda el navegador: nada que no sea un filtro conocido y legible."""
        raw = raw if isinstance(raw, dict) else {}
        today = fields.Date.context_today(self)
        period = periodos.periodo_valido(raw.get("period") or "30")
        date_from = date_to = None
        if period == "rango":
            try:
                date_from = fields.Date.to_date(raw.get("date_from") or None)
                date_to = fields.Date.to_date(raw.get("date_to") or None)
            except (TypeError, ValueError):
                date_from = date_to = None
        start, end = periodos.rango(period, today, date_from, date_to)
        Service = self.env["mirabilenet.service"]
        states = dict(Service._fields["state"].selection)
        modes = dict(Service._fields["payment_mode"].selection)
        region = self.env["mirabilenet.region"]
        if self.env.user.mirabilenet_is_global:
            region = self._mirabilenet_record("mirabilenet.region", raw.get("region_id"))
        return {
            "period": period, "start": start, "end": end, "today": today,
            "region": region,
            "zone": self._mirabilenet_record("mirabilenet.zone", raw.get("zone_id")),
            "node": self._mirabilenet_record("mirabilenet.node", raw.get("node_id")),
            "plan": self._mirabilenet_record("product.template", raw.get("plan_id")),
            "payment_mode": raw.get("payment_mode") if raw.get("payment_mode") in modes else False,
            "service_state": (raw.get("service_state") if raw.get("service_state") in states
                              else False),
        }

    @api.model
    def _mirabilenet_service_values(self, f):
        """Los filtros que se aplican a través del servicio: {campo del servicio: valor}."""
        values = {}
        for key, field in SERVICE_FILTERS:
            value = f.get(key)
            if isinstance(value, models.BaseModel):
                value = value.id
            if value:
                values[field] = value
        return values

    @api.model
    def _mirabilenet_scope(self, model, domain, f):
        domain = list(domain)
        region = f["region"]
        if region and model in REGION_FIELDS:
            field = REGION_FIELDS[model]
            if model == "product.template":
                # Un plan sin región se ofrece en todas.
                domain += ["|", (field, "=", False), (field, "=", region.id)]
            else:
                domain.append((field, "=", region.id))
        if model in SERVICE_PATHS:
            prefix = SERVICE_PATHS[model]
            for field, value in self._mirabilenet_service_values(f).items():
                domain.append((prefix + field, "=", value))
        elif model == "mirabilenet.node":
            if f["zone"]:
                domain.append(("zone_id", "=", f["zone"].id))
            if f["node"]:
                domain.append(("id", "=", f["node"].id))
        elif model == "product.template" and f["plan"]:
            domain.append(("id", "=", f["plan"].id))
        return domain

    @api.model
    def _mirabilenet_can(self, model):
        return model in self.env and self.env[model].has_access("read")

    # -- Los dominios: el número de cada tarjeta y la lista que abre ---------------------
    @api.model
    def _mirabilenet_domains(self, f):
        start, end, today = f["start"], f["end"], f["today"]
        month = periodos.inicio_de_mes(today)
        open_moves = self.env["account.move"]._mirabilenet_open_domain()
        inbound = [("payment_type", "=", "inbound"), ("state", "in", PAYMENT_STATES)]
        customer = [("mirabilenet_is_customer", "=", True)]
        invoices = [("move_type", "=", "out_invoice"), ("state", "=", "posted")]
        domains = {
            "servicios_activos": ("mirabilenet.service", [("state", "=", "activo")],
                                  _("Servicios activos")),
            "servicios_total": ("mirabilenet.service", [], _("Servicios")),
            "servicios_facturan": ("mirabilenet.service", [("state", "in", BILLING_STATES)],
                                   _("Servicios que facturan")),
            "instalaciones_pendientes": ("mirabilenet.service",
                                         [("state", "=", "pendiente_instalacion")],
                                         _("Instalaciones pendientes")),
            "altas_periodo": ("mirabilenet.service", [("date_start", ">=", start),
                                                      ("date_start", "<=", end)],
                              _("Altas del periodo")),
            "altas_hoy": ("mirabilenet.service", [("date_start", "=", today)], _("Altas de hoy")),
            "altas_mes": ("mirabilenet.service", [("date_start", ">=", month),
                                                  ("date_start", "<=", today)],
                          _("Altas del mes")),
            "bajas_periodo": ("mirabilenet.service", [("state", "=", "baja"),
                                                      ("date_end", ">=", start),
                                                      ("date_end", "<=", end)],
                              _("Bajas del periodo")),
            "pagos_periodo": ("account.payment", inbound + [("date", ">=", start),
                                                            ("date", "<=", end)],
                              _("Cobros del periodo")),
            "pagos_hoy": ("account.payment", inbound + [("date", "=", today)],
                          _("Cobrado hoy")),
            "pagos_mes": ("account.payment", inbound + [("date", ">=", month),
                                                        ("date", "<=", today)],
                          _("Cobrado del mes")),
            "pagos": ("account.payment", inbound, _("Pagos")),
            "facturado_periodo": ("account.move", invoices + [("invoice_date", ">=", start),
                                                              ("invoice_date", "<=", end)],
                                  _("Facturado en el periodo")),
            "cartera_vencida": ("account.move", open_moves + [("invoice_date_due", "<", today)],
                                _("Cartera vencida")),
            "vencidas_30": ("account.move", open_moves + [
                ("invoice_date_due", "<", today - timedelta(days=30))],
                _("Vencidas hace más de 30 días")),
            "vence_7": ("account.move", open_moves + [
                ("invoice_date_due", ">=", today),
                ("invoice_date_due", "<=", today + timedelta(days=7))], _("Vence en 7 días")),
            "gastos": ("account.move", [("move_type", "=", "in_invoice"),
                                        ("state", "=", "posted")],
                       _("Gastos (facturas de proveedor)")),
            "clientes_total": ("res.partner", customer, _("Clientes")),
            "comprobantes_revision": ("mirabilenet.whatsapp.proof", [("state", "=", "revision")],
                                      _("Pagos por aprobar")),
            "routers_total": ("mirabilenet.router", [("state", "!=", "retirado")], _("Routers")),
            "routers_conectados": ("mirabilenet.router", [("state", "=", "conectado")],
                                   _("Routers conectados")),
            "routers_alerta": ("mirabilenet.router",
                               [("state", "in", ("degradado", "desconectado"))],
                               _("Routers degradados o desconectados")),
            "pppoe_total": ("mirabilenet.pppoe.account", [], _("Cuentas PPPoE")),
            "pppoe_desincronizadas": ("mirabilenet.pppoe.account", [("synced", "=", False)],
                                      _("Cuentas desincronizadas")),
            "averias_abiertas": ("maintenance.request", [("stage_id.done", "=", False),
                                                         ("mirabilenet_service_id", "!=", False)],
                                 _("Averías abiertas")),
            "casos_abiertos": ("mirabilenet.support.case", [("state", "!=", "resuelto")],
                               _("Casos de soporte abiertos")),
            "regiones": ("mirabilenet.region", [], _("Regiones")),
            "sucursales": ("mirabilenet.branch", [], _("Sucursales")),
            "nodos": ("mirabilenet.node", [], _("Nodos")),
            "nodos_con_capacidad": ("mirabilenet.node", [("capacidad_instalada", ">", 0)],
                                    _("Nodos con capacidad")),
            "planes": ("product.template", [("mirabilenet_is_plan", "=", True)], _("Planes")),
            "cajas": ("pos.config", [("mirabilenet_branch_id", "!=", False)], _("Cajas")),
            "puertos_ocupados": ("mirabilenet.fiber.port", [("state", "=", "ocupado")],
                                 _("Puertos NAP ocupados")),
            "puertos_total": ("mirabilenet.fiber.port", [], _("Puertos NAP")),
            "actividad": ("mirabilenet.audit.log", [], _("Auditoría")),
        }
        for state, label in self.env["mirabilenet.service"]._fields["state"].selection:
            domains["servicios_%s" % state] = ("mirabilenet.service", [("state", "=", state)],
                                               _("Servicios: %s", label))
        titles = {"prospectos": _("Prospectos"), "instalacion": _("Clientes por instalar"),
                  "activos": _("Clientes activos"), "morosos": _("Clientes morosos"),
                  "suspendidos": _("Clientes suspendidos"), "bajas": _("Bajas")}
        for key, states in CUSTOMER_GROUPS.items():
            domains["clientes_%s" % key] = ("res.partner",
                                            customer + [("mirabilenet_state", "in", states)],
                                            titles[key])
        for key, label, low, high in negocio.TRAMOS:
            due = [("invoice_date_due", "<=", today - timedelta(days=max(low, 1)))]
            if high is not None:
                due.append(("invoice_date_due", ">=", today - timedelta(days=high)))
            domains["cartera_%s" % key] = ("account.move", open_moves + due,
                                           _("Cartera vencida: %s", label))
        return {key: (model, self._mirabilenet_scope(model, domain, f), title)
                for key, (model, domain, title) in domains.items()}

    @api.model
    def _mirabilenet_count(self, domains, key):
        model, domain, _title = domains[key]
        if not self._mirabilenet_can(model):
            return None
        return self.env[model].search_count(domain)

    @api.model
    def _mirabilenet_sum(self, domains, key, field):
        model, domain, _title = domains[key]
        if not self._mirabilenet_can(model):
            return None
        [[total]] = self.env[model]._read_group(domain, aggregates=["%s:sum" % field])
        return total or 0.0

    # -- La pantalla ------------------------------------------------------------
    @api.model
    def get_dashboard_data(self, filters=None):
        f = self._mirabilenet_filters(filters)
        domains = self._mirabilenet_domains(f)
        count = lambda key: self._mirabilenet_count(domains, key)  # noqa: E731
        # El mismo periodo, justo antes: para ▲▼.
        prev_start, prev_end = periodos.anterior(f["start"], f["end"])
        previous = self._mirabilenet_domains(dict(f, start=prev_start, end=prev_end))
        user = self.env.user
        income = self._mirabilenet_sum(domains, "pagos_periodo", "amount")
        income_before = self._mirabilenet_sum(previous, "pagos_periodo", "amount")
        new = count("altas_periodo")
        new_before = self._mirabilenet_count(previous, "altas_periodo")
        return {
            "generado": fields.Datetime.to_string(fields.Datetime.now()),
            "filtros": self._mirabilenet_filters_echo(f),
            "es_global": user.mirabilenet_is_global,
            "titulo_region": f["region"].name or (user.mirabilenet_region_id.name
                                                  if not user.mirabilenet_is_global
                                                  else _("Todas las regiones")),
            "moneda": self._mirabilenet_currency(f["region"]),
            "secciones": self._mirabilenet_layout(),
            "alertas": self._mirabilenet_alerts(domains, f),
            "resumen": {
                "clientes_activos": count("servicios_activos"),
                "ingresos": income,
                "ingresos_variacion": negocio.variacion(income, income_before),
                "servicios_total": count("servicios_total"),
                "cartera_vencida": self._mirabilenet_sum(domains, "cartera_vencida",
                                                         "amount_residual"),
                "altas": new,
                "altas_variacion": negocio.variacion(new, new_before),
            },
            "negocio": self._mirabilenet_business(domains, previous, f),
            "ingresos_gastos": self._mirabilenet_income_expense(f),
            "servicios_estado": self._mirabilenet_service_states(domains),
            "actividad": self._mirabilenet_activity(domains),
            "puesta_en_marcha": self._mirabilenet_setup(domains),
            "cobranza_diaria": self._mirabilenet_daily(domains, f),
            "cobranza_metodo": self._mirabilenet_methods(domains),
            "clientes": dict({key: count(key) for key in (
                "clientes_total", "clientes_prospectos", "clientes_instalacion",
                "clientes_activos", "clientes_morosos", "clientes_suspendidos",
                "clientes_bajas")}, altas_hoy=count("altas_hoy"), altas_mes=count("altas_mes")),
            "cobros": self._mirabilenet_collections(domains),
            "red": self._mirabilenet_network(domains),
            "capacidad": self._mirabilenet_capacity(domains, f),
            "soporte": {
                "averias_abiertas": count("averias_abiertas"),
                "casos_abiertos": count("casos_abiertos"),
                "instalaciones_pendientes": count("instalaciones_pendientes"),
            },
            "cartera": self._mirabilenet_overdue(domains, f),
            "ultimos_pagos": self._mirabilenet_last_payments(domains),
        }

    @api.model
    def _mirabilenet_filters_echo(self, f):
        """Los filtros que de verdad se aplicaron, con sus nombres, para los chips."""
        Service = self.env["mirabilenet.service"]
        chips = []
        for key, record in (("region_id", f["region"]), ("zone_id", f["zone"]),
                            ("node_id", f["node"]), ("plan_id", f["plan"])):
            if record:
                chips.append({"clave": key, "valor": record.id, "etiqueta": record.display_name})
        if f["payment_mode"]:
            chips.append({"clave": "payment_mode", "valor": f["payment_mode"], "etiqueta": dict(
                Service._fields["payment_mode"].selection)[f["payment_mode"]]})
        if f["service_state"]:
            chips.append({"clave": "service_state", "valor": f["service_state"],
                          "etiqueta": _("Estado: %s", dict(
                              Service._fields["state"].selection)[f["service_state"]])})
        return {"period": f["period"], "desde": fields.Date.to_string(f["start"]),
                "hasta": fields.Date.to_string(f["end"]), "chips": chips}

    @api.model
    def _mirabilenet_currency(self, region):
        """La moneda de las regiones (bolivianos), no la de la compañía."""
        region = region or self.env.user.mirabilenet_region_id or \
            self.env["mirabilenet.region"].search([], limit=1)
        currency = region.currency_id or self.env.company.currency_id
        return currency.symbol or currency.name or ""

    @api.model
    def _mirabilenet_layout(self):
        """Orden de las secciones para el rol del usuario y lo que ocultó."""
        prefs = self._mirabilenet_prefs()
        order = list(ROLE_LAYOUTS.get(self.env.user.mirabilenet_role, SECTIONS))
        order += [s for s in SECTIONS if s not in order]
        hidden = [s for s in prefs.get("ocultas", []) if s in SECTIONS]
        return {"orden": order, "ocultas": hidden, "rol": self.env.user.mirabilenet_role or ""}

    # -- Alertas: solo lo que pide atención ahora -----------------------------------------
    @api.model
    def _mirabilenet_alerts(self, domains, f):
        alerts = []

        def add(key, level, text, count):
            if count:
                alerts.append({"clave": key, "nivel": level, "texto": text, "cantidad": count})

        add("routers_alerta", "danger", _("Routers degradados o desconectados"),
            self._mirabilenet_count(domains, "routers_alerta"))
        add("comprobantes_revision", "warning", _("Comprobantes de pago por revisar"),
            self._mirabilenet_count(domains, "comprobantes_revision"))
        add("vencidas_30", "danger", _("Facturas vencidas hace más de 30 días"),
            self._mirabilenet_count(domains, "vencidas_30"))
        naps = self._mirabilenet_nap_faults(domains, minimum=2)
        if naps:
            alerts.append({"clave": "averias_abiertas", "nivel": "warning",
                           "texto": _("Cajas NAP con 2 o más averías: %s",
                                      ", ".join(n["nombre"] for n in naps[:3])),
                           "cantidad": len(naps)})
        goal = self._mirabilenet_goal(f)
        if goal and goal["objetivo"] and goal["mrr"] < goal["objetivo"]:
            alerts.append({"clave": "servicios_facturan", "nivel": "info",
                           "texto": _("Ingreso mensual al %s %% del objetivo", goal["avance"]),
                           "cantidad": None})
        return alerts

    @api.model
    def _mirabilenet_nap_faults(self, domains, minimum=1):
        model, domain, _title = domains["averias_abiertas"]
        if not self._mirabilenet_can(model) or not self._mirabilenet_can("mirabilenet.fiber.nap"):
            return []
        rows = self.env[model]._read_group(
            domain + [("mirabilenet_fiber_nap_id", "!=", False)], ["mirabilenet_fiber_nap_id"],
            ["__count"], order="__count desc")
        return [{"id": nap.id, "nombre": nap.display_name, "cantidad": total}
                for nap, total in rows if total >= minimum]

    # -- Negocio ---------------------------------------------------------------------
    @api.model
    def _mirabilenet_goal(self, f):
        """MRR de los servicios que facturan y el objetivo de las regiones en pantalla."""
        if not self._mirabilenet_can("mirabilenet.service"):
            return None
        domain = self._mirabilenet_scope("mirabilenet.service",
                                         [("state", "in", BILLING_STATES)], f)
        [[mrr, services]] = self.env["mirabilenet.service"]._read_group(
            domain, aggregates=["monthly_price:sum", "__count"])
        regions = f["region"] or self.env["mirabilenet.region"].search([])
        # Con filtros de plan, nodo o estado, el objetivo de la región ya no se compara.
        filtered = bool(self._mirabilenet_service_values(f))
        goal = 0.0 if filtered else sum(regions.mapped("objetivo_mrr"))
        return {"mrr": mrr or 0.0, "servicios": services, "objetivo": goal or None,
                "avance": periodos.porcentaje(mrr, goal) if goal else None}

    @api.model
    def _mirabilenet_business(self, domains, previous, f):
        goal = self._mirabilenet_goal(f)
        if goal is None:
            return None
        billed = self._mirabilenet_sum(domains, "facturado_periodo", "amount_total")
        collected = self._mirabilenet_sum(domains, "pagos_periodo", "amount")
        rate = negocio.recaudacion(collected, billed)
        rate_before = negocio.recaudacion(
            self._mirabilenet_sum(previous, "pagos_periodo", "amount"),
            self._mirabilenet_sum(previous, "facturado_periodo", "amount_total"))
        months = self._mirabilenet_movements(f)
        current = months[-1] if months else {}
        return {
            "mrr": goal["mrr"],
            "objetivo": goal["objetivo"],
            "avance": goal["avance"],
            "arpu": negocio.arpu(goal["mrr"], goal["servicios"]),
            "churn": current.get("churn"),
            "bajas_mes": current.get("bajas"),
            "altas_mes": current.get("altas"),
            "facturado": billed,
            "recaudacion": rate,
            "recaudacion_variacion": (round(rate - rate_before, 1)
                                      if rate is not None and rate_before is not None else None),
            "movimientos": months,
            "antiguedad": self._mirabilenet_aging(domains, f),
            "top_mora": self._mirabilenet_top_debt(domains),
            "top_averias": self._mirabilenet_nap_faults(domains)[:TOP_LIMIT],
        }

    @api.model
    def _mirabilenet_movements(self, f):
        """Altas, bajas, altas netas y churn de los últimos 6 meses."""
        Service = self.env["mirabilenet.service"]
        base = self._mirabilenet_scope("mirabilenet.service", [], f)
        base = [d for d in base if not (isinstance(d, tuple) and d[0] == "state")]
        rows = []
        for first, last, label in periodos.meses_atras(f["today"], 6):
            new = Service.search_count(base + [("date_start", ">=", first),
                                               ("date_start", "<=", last)])
            gone = Service.search_count(base + [("state", "=", "baja"), ("date_end", ">=", first),
                                                ("date_end", "<=", last)])
            at_start = Service.search_count(base + [
                ("date_start", "<", first), ("state", "!=", "pendiente_instalacion"),
                "|", ("date_end", "=", False), ("date_end", ">=", first)])
            rows.append({"etiqueta": label, "altas": new, "bajas": gone, "netas": new - gone,
                         "churn": negocio.churn(gone, at_start),
                         "desde": fields.Date.to_string(first),
                         "hasta": fields.Date.to_string(last)})
        return rows

    @api.model
    def _mirabilenet_aging(self, domains, f):
        model, domain, _title = domains["cartera_vencida"]
        if not self._mirabilenet_can(model):
            return None
        moves = self.env[model].search_read(domain, ["invoice_date_due", "amount_residual",
                                                     "partner_id"])
        return negocio.antiguedad(
            ((m["invoice_date_due"], m["amount_residual"],
              m["partner_id"] and m["partner_id"][0]) for m in moves), f["today"])

    @api.model
    def _mirabilenet_top_debt(self, domains):
        """Las zonas con más deuda vencida (por el nodo del servicio)."""
        model, domain, _title = domains["cartera_vencida"]
        if not self._mirabilenet_can(model):
            return None
        totals = {}
        for move in self.env[model].search(domain):
            zone = move.mirabilenet_service_id.node_id.zone_id
            name = zone.display_name if zone else _("Sin zona asignada")
            totals[name] = totals.get(name, 0.0) + move.amount_residual
        return [{"nombre": name, "monto": amount}
                for name, amount in sorted(totals.items(), key=lambda x: -x[1])[:TOP_LIMIT]]

    # -- Secciones -----------------------------------------------------------------------
    @api.model
    def _mirabilenet_service_states(self, domains):
        model, domain, _title = domains["servicios_total"]
        if not self._mirabilenet_can(model):
            return None
        # El filtro de estado no aplica a la distribución: se ve el total para elegir otro.
        domain = [d for d in domain if not (isinstance(d, tuple) and d[0] == "state")]
        counts = dict(self.env[model]._read_group(domain, ["state"], ["__count"]))
        return [{"clave": state, "etiqueta": label, "cantidad": counts.get(state, 0)}
                for state, label in self.env[model]._fields["state"].selection]

    @api.model
    def _mirabilenet_income_expense(self, f):
        Payment, Move = self.env["account.payment"], self.env["account.move"]
        if not self._mirabilenet_can("account.payment"):
            return None
        months = periodos.meses_atras(f["today"], 6)
        start, end = months[0][0], months[-1][1]
        inbound = self._mirabilenet_scope("account.payment", [
            ("payment_type", "=", "inbound"), ("state", "in", PAYMENT_STATES),
            ("date", ">=", start), ("date", "<=", end)], f)
        income = {m.replace(day=1): total for m, total in Payment._read_group(
            inbound, ["date:month"], ["amount:sum"])}
        expenses, has_expenses = {}, False
        if self._mirabilenet_can("account.move"):
            bills = self._mirabilenet_scope("account.move", [
                ("move_type", "=", "in_invoice"), ("state", "=", "posted"),
                ("invoice_date", ">=", start), ("invoice_date", "<=", end)], f)
            expenses = {m.replace(day=1): total for m, total in Move._read_group(
                bills, ["invoice_date:month"], ["amount_total_signed:sum"])}
            has_expenses = bool(expenses)
        rows = []
        for first, last, label in months:
            rows.append({"etiqueta": label, "ingresos": income.get(first, 0.0),
                         "desde": fields.Date.to_string(first),
                         "hasta": fields.Date.to_string(last),
                         "gastos": abs(expenses[first]) if first in expenses else
                         (0.0 if has_expenses else None)})
        total_in = sum(r["ingresos"] for r in rows)
        total_out = sum(r["gastos"] or 0.0 for r in rows) if has_expenses else None
        return {"meses": rows, "con_gastos": has_expenses,
                "con_movimientos": bool(total_in or total_out),
                "margen": (total_in - total_out) if has_expenses else None,
                "ingresos": total_in, "gastos": total_out}

    @api.model
    def _mirabilenet_activity(self, domains):
        model, domain, _title = domains["actividad"]
        if not self._mirabilenet_can(model):
            return None
        logs = self.env[model].search(domain, order="create_date desc, id desc",
                                      limit=ACTIVITY_LIMIT)
        return [{"id": log.id, "accion": log.action, "descripcion": log.description or "",
                 "usuario": log.user_id.name or "",
                 "fecha": fields.Datetime.to_string(log.create_date)} for log in logs]

    @api.model
    def _mirabilenet_setup(self, domains):
        """Los ocho pasos para dejar una región funcionando, con lo que falta en cada uno."""
        count = lambda key: self._mirabilenet_count(domains, key)  # noqa: E731
        regions, branches = count("regiones"), count("sucursales")
        nodes, with_capacity = count("nodos"), count("nodos_con_capacidad")
        routers, connected = count("routers_total"), count("routers_conectados")
        plans, cash, customers = count("planes"), count("cajas"), count("clientes_total")
        services = count("servicios_activos")
        missing = ""
        if "mirabilenet.web.settings" in self.env and self.env.user.has_group("base.group_user"):
            settings = self.env["mirabilenet.web.settings"]._load()
            missing = settings.missing_data or ""
        steps = [
            ("region", _("Crear la región y la sucursal"), bool(regions and branches),
             _("%(r)s región(es) y %(s)s sucursal(es) activas", r=regions or 0, s=branches or 0),
             "mirabilenet_base.action_mirabilenet_region"),
            ("capacidad", _("Declarar la capacidad de los nodos"), bool(with_capacity),
             _("%(c)s de %(n)s nodo(s) con capacidad", c=with_capacity or 0, n=nodes or 0)
             if nodes else _("Sin esto no se puede calcular la ocupación"),
             "mirabilenet_base.action_mirabilenet_node"),
            ("planes", _("Definir los planes comerciales"), bool(plans),
             _("%s plan(es) activo(s)", plans or 0), "mirabilenet_isp.action_mirabilenet_plan"),
            ("router", _("Registrar y enrolar el primer router"), bool(connected),
             _("%(r)s registrado(s), %(c)s conectado(s)", r=routers or 0, c=connected or 0),
             "mirabilenet_isp.action_mirabilenet_router"),
            ("caja", _("Abrir una caja para cobrar"), bool(cash),
             _("%s caja(s) activa(s)", cash or 0), "point_of_sale.action_pos_config_kanban"),
            ("cliente", _("Cargar el primer cliente"), bool(customers),
             _("%s cliente(s)", customers or 0), "mirabilenet_isp.action_mirabilenet_customer"),
            ("servicio", _("Activar el primer servicio"), bool(services),
             _("%s servicio(s) activo(s)", services or 0),
             "mirabilenet_isp.action_mirabilenet_service"),
            ("web", _("Completar los datos de contacto de la web"), not missing,
             _("Faltan: %s", missing) if missing else _("Completos"),
             "mirabilenet_web.action_web_settings"),
        ]
        result = [{"clave": key, "titulo": title, "hecho": done, "detalle": detail,
                   "accion": action} for key, title, done, detail, action in steps]
        done = sum(1 for step in result if step["hecho"])
        return {"pasos": result, "hechos": done, "total": len(result),
                "router_listo": bool(connected)}

    @api.model
    def _mirabilenet_daily(self, domains, f):
        model, domain, _title = domains["pagos"]
        if not self._mirabilenet_can(model):
            return None
        # Con «hoy» o 7 días un punto suelto no dice nada: se muestran 30 días.
        start, end = f["start"], f["end"]
        if (end - start).days < 29:
            start, end = periodos.rango("30", f["today"])
        domain = domain + [("date", ">=", start), ("date", "<=", end)]
        totals = {d: total for d, total in self.env[model]._read_group(
            domain, ["date:day"], ["amount:sum"])}
        days = [{"fecha": fields.Date.to_string(d), "monto": totals.get(d, 0.0)}
                for d in periodos.dias(start, end)]
        return {"dias": days, "total": sum(d["monto"] for d in days),
                "desde": fields.Date.to_string(start), "hasta": fields.Date.to_string(end)}

    @api.model
    def _mirabilenet_methods(self, domains):
        model, domain, _title = domains["pagos_periodo"]
        if not self._mirabilenet_can(model):
            return None
        totals = {}
        for journal, total in self.env[model]._read_group(domain, ["journal_id"],
                                                         ["amount:sum"]):
            if journal.type == "cash":
                label = _("Efectivo")
            elif "qr" in (journal.name or "").lower():
                label = _("QR")
            else:
                label = _("Transferencia")
            totals[label] = totals.get(label, 0.0) + (total or 0.0)
        return [{"etiqueta": label, "monto": amount}
                for label, amount in sorted(totals.items(), key=lambda x: -x[1])]

    @api.model
    def _mirabilenet_collections(self, domains):
        return {
            "hoy": self._mirabilenet_sum(domains, "pagos_hoy", "amount"),
            "mes": self._mirabilenet_sum(domains, "pagos_mes", "amount"),
            "por_aprobar": self._mirabilenet_count(domains, "comprobantes_revision"),
            "vence_7": self._mirabilenet_sum(domains, "vence_7", "amount_residual"),
        }

    @api.model
    def _mirabilenet_network(self, domains):
        count = lambda key: self._mirabilenet_count(domains, key)  # noqa: E731
        connected = count("routers_conectados")
        return {
            "routers_total": count("routers_total"),
            "routers_conectados": connected,
            "pppoe_total": count("pppoe_total"),
            # Sin un router conectado no hay con qué comparar: no es una diferencia real.
            "pppoe_desincronizadas": count("pppoe_desincronizadas") if connected else None,
            # Todavía no se leen del router: se dice, no se pone 0.
            "sesiones_en_linea": None,
            "trafico": None,
        }

    @api.model
    def _mirabilenet_capacity(self, domains, f):
        model, domain, _title = domains["nodos"]
        installed = None
        if self._mirabilenet_can(model):
            installed = sum(self.env[model].search(domain).mapped("capacidad_instalada")) or None
        used = None
        if self._mirabilenet_can("mirabilenet.service"):
            used = self.env["mirabilenet.service"].search_count(self._mirabilenet_scope(
                "mirabilenet.service", [("state", "in", OPEN_SERVICE_STATES)], f))
        ports_used = self._mirabilenet_count(domains, "puertos_ocupados")
        ports_total = self._mirabilenet_count(domains, "puertos_total")
        return {
            "instalada": installed,
            "ocupada": used,
            "disponible": periodos.disponible(installed, used),
            "ocupacion": periodos.porcentaje(used, installed),
            "puertos_ocupados": ports_used,
            "puertos_total": ports_total or None,
            "ocupacion_puertos": periodos.porcentaje(ports_used, ports_total),
        }

    @api.model
    def _mirabilenet_overdue(self, domains, f):
        model, domain, _title = domains["cartera_vencida"]
        if not self._mirabilenet_can(model):
            return None
        rows = []
        for partner, total, oldest in self.env[model]._read_group(
                domain, ["partner_id"], ["amount_residual:sum", "invoice_date_due:min"],
                order="amount_residual:sum desc", limit=OVERDUE_LIMIT):
            rows.append({"cliente": partner.display_name, "monto": total,
                         "dias": (f["today"] - oldest).days if oldest else None})
        return {"total": self._mirabilenet_sum(domains, "cartera_vencida", "amount_residual"),
                "clientes": rows}

    @api.model
    def _mirabilenet_last_payments(self, domains):
        model, domain, _title = domains["pagos"]
        if not self._mirabilenet_can(model):
            return None
        payments = self.env[model].search(domain, order="date desc, id desc",
                                          limit=LAST_PAYMENTS_LIMIT)
        return [{"id": p.id, "cliente": p.partner_id.display_name or "",
                 "monto": p.amount, "fecha": fields.Date.to_string(p.date),
                 "metodo": p.journal_id.name or "", "referencia": p.name or ""}
                for p in payments]

    # -- Opciones de los filtros y preferencias ------------------------------------------
    @api.model
    def get_filter_options(self):
        """Lo que el usuario puede elegir en cada filtro (solo lo que puede leer)."""
        Service = self.env["mirabilenet.service"]

        def options(model, domain, region_field="region_id", zone=False):
            if not self._mirabilenet_can(model):
                return []
            rows = []
            for record in self.env[model].search(domain, order="name", limit=300):
                row = {"id": record.id, "name": record.display_name,
                       "region_id": record[region_field].id if region_field else False}
                if zone:
                    row["zone_id"] = record.zone_id.id
                rows.append(row)
            return rows

        return {
            "regiones": (options("mirabilenet.region", [], region_field=None)
                         if self.env.user.mirabilenet_is_global else []),
            "zonas": options("mirabilenet.zone", []),
            "nodos": options("mirabilenet.node", [], zone=True),
            "planes": options("product.template", [("mirabilenet_is_plan", "=", True)],
                              region_field="mirabilenet_region_id"),
            "modalidades": [{"id": k, "name": v}
                            for k, v in Service._fields["payment_mode"].selection],
            "estados": [{"id": k, "name": v} for k, v in Service._fields["state"].selection],
            "secciones": list(SECTIONS),
            "preferencias": self._mirabilenet_prefs(),
        }

    @api.model
    def _mirabilenet_prefs(self):
        settings = self.env["res.users.settings"]._find_or_create_for_user(self.env.user)
        prefs = settings.mirabilenet_dashboard_prefs
        return prefs if isinstance(prefs, dict) else {}

    @api.model
    def save_preferences(self, prefs):
        """Guarda los filtros y las secciones ocultas del usuario (solo claves conocidas)."""
        prefs = prefs if isinstance(prefs, dict) else {}
        raw = prefs.get("filtros") if isinstance(prefs.get("filtros"), dict) else {}
        clean = {
            "filtros": {k: raw[k] for k in PREF_FILTERS if raw.get(k) not in (None, "", False)},
            "ocultas": [s for s in prefs.get("ocultas") or [] if s in SECTIONS],
        }
        settings = self.env["res.users.settings"]._find_or_create_for_user(self.env.user)
        settings.mirabilenet_dashboard_prefs = clean
        return clean

    # -- Abrir la lista de una tarjeta ---------------------------------------------
    @api.model
    def action_open(self, key, filters=None):
        f = self._mirabilenet_filters(filters)
        domains = self._mirabilenet_domains(f)
        if key not in domains:
            raise UserError(_("Ese indicador no existe."))
        model, domain, title = domains[key]
        if not self._mirabilenet_can(model):
            raise UserError(_("No tiene acceso a esta información."))
        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": model,
            "domain": domain,
            "views": [(False, "list"), (False, "form")],
            "target": "current",
            "context": {"create": False},
        }
