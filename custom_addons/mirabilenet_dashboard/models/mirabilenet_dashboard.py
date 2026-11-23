"""Los números del dashboard. Todo se lee con los permisos del usuario (sin sudo): cada uno ve
solo su región, y los usuarios globales pueden elegir una región o ver todas.

Regla de los indicadores de MIRABILENET: lo que no tiene datos va como None (la pantalla
muestra «—» con su aviso), nunca como 0.
"""
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tablero import periodos

PAYMENT_STATES = ("in_process", "paid")
OPEN_SERVICE_STATES = ("activo", "suspendido", "moroso")
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
#: Campo de región de cada modelo, para cuando un usuario global elige una región.
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
    "mirabilenet.branch": "region_id",
    "mirabilenet.audit.log": "region_id",
    "pos.config": "mirabilenet_region_id",
    "maintenance.request": "mirabilenet_service_id.region_id",
    "mirabilenet.fiber.port": "nap_id.region_id",
    "product.template": "mirabilenet_region_id",
    "mirabilenet.region": "id",
}


class MirabilenetDashboard(models.AbstractModel):
    _name = "mirabilenet.dashboard"
    _description = "Dashboard de MIRABILENET"

    # -- Alcance ----------------------------------------------------------------
    @api.model
    def _mirabilenet_region(self, region_id):
        """La región elegida, solo para usuarios globales. El resto ve lo que sus reglas dejan."""
        if not region_id or not self.env.user.mirabilenet_is_global:
            return self.env["mirabilenet.region"]
        region = self.env["mirabilenet.region"].browse(int(region_id)).exists()
        return region if region.has_access("read") else self.env["mirabilenet.region"]

    @api.model
    def _mirabilenet_can(self, model):
        return model in self.env and self.env[model].has_access("read")

    @api.model
    def _mirabilenet_scope(self, model, domain, region):
        if region and model in REGION_FIELDS:
            field = REGION_FIELDS[model]
            if model == "product.template":
                # Un plan sin región se ofrece en todas.
                return domain + ["|", (field, "=", False), (field, "=", region.id)]
            return domain + [(field, "=", region.id)]
        return domain

    # -- Los dominios: el número de cada tarjeta y la lista que abre ---------------------
    @api.model
    def _mirabilenet_domains(self, period, region):
        today = fields.Date.context_today(self)
        start, end = periodos.rango(period, today)
        month = periodos.inicio_de_mes(today)
        day_start = fields.Datetime.to_datetime(today)
        month_start = fields.Datetime.to_datetime(month)
        open_moves = self.env["account.move"]._mirabilenet_open_domain()
        inbound = [("payment_type", "=", "inbound"), ("state", "in", PAYMENT_STATES)]
        customer = [("mirabilenet_is_customer", "=", True)]
        domains = {
            "servicios_activos": ("mirabilenet.service", [("state", "=", "activo")],
                                  _("Servicios activos")),
            "servicios_total": ("mirabilenet.service", [], _("Servicios")),
            "instalaciones_pendientes": ("mirabilenet.service",
                                         [("state", "=", "pendiente_instalacion")],
                                         _("Instalaciones pendientes")),
            "pagos_periodo": ("account.payment", inbound + [("date", ">=", start),
                                                            ("date", "<=", end)],
                              _("Cobros del periodo")),
            "pagos_hoy": ("account.payment", inbound + [("date", "=", today)],
                          _("Cobrado hoy")),
            "pagos_mes": ("account.payment", inbound + [("date", ">=", month),
                                                        ("date", "<=", today)],
                          _("Cobrado del mes")),
            "cartera_vencida": ("account.move", open_moves + [("invoice_date_due", "<", today)],
                                _("Cartera vencida")),
            "vence_7": ("account.move", open_moves + [
                ("invoice_date_due", ">=", today),
                ("invoice_date_due", "<=", today + timedelta(days=7))], _("Vence en 7 días")),
            "gastos": ("account.move", [("move_type", "=", "in_invoice"),
                                        ("state", "=", "posted")], _("Gastos (facturas de proveedor)")),
            "clientes_total": ("res.partner", customer, _("Clientes")),
            "clientes_nuevos_hoy": ("res.partner", customer + [("create_date", ">=", day_start)],
                                    _("Clientes nuevos de hoy")),
            "clientes_nuevos_mes": ("res.partner", customer + [("create_date", ">=", month_start)],
                                    _("Clientes nuevos del mes")),
            "comprobantes_revision": ("mirabilenet.whatsapp.proof", [("state", "=", "revision")],
                                      _("Pagos por aprobar")),
            "routers_total": ("mirabilenet.router", [("state", "!=", "retirado")], _("Routers")),
            "routers_conectados": ("mirabilenet.router", [("state", "=", "conectado")],
                                   _("Routers conectados")),
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
        for state, _label in self.env["mirabilenet.service"]._fields["state"].selection:
            domains["servicios_%s" % state] = ("mirabilenet.service", [("state", "=", state)],
                                               _("Servicios: %s", _label))
        titles = {"prospectos": _("Prospectos"), "instalacion": _("Clientes por instalar"),
                  "activos": _("Clientes activos"), "morosos": _("Clientes morosos"),
                  "suspendidos": _("Clientes suspendidos"), "bajas": _("Bajas")}
        for key, states in CUSTOMER_GROUPS.items():
            domains["clientes_%s" % key] = ("res.partner",
                                            customer + [("mirabilenet_state", "in", states)],
                                            titles[key])
        return {key: (model, self._mirabilenet_scope(model, domain, region), title)
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
    def get_dashboard_data(self, period="30", region_id=False):
        period = periodos.periodo_valido(period)
        region = self._mirabilenet_region(region_id)
        domains = self._mirabilenet_domains(period, region)
        today = fields.Date.context_today(self)
        count = lambda key: self._mirabilenet_count(domains, key)  # noqa: E731
        user = self.env.user
        regions = []
        if user.mirabilenet_is_global:
            regions = [{"id": r.id, "name": r.name}
                       for r in self.env["mirabilenet.region"].search([], order="name")]
        return {
            "generado": fields.Datetime.to_string(fields.Datetime.now()),
            "periodo": period,
            "es_global": user.mirabilenet_is_global,
            "regiones": regions,
            "region": {"id": region.id, "name": region.name} if region else None,
            "titulo_region": region.name or (user.mirabilenet_region_id.name
                                             if not user.mirabilenet_is_global
                                             else _("Todas las regiones")),
            "moneda": self._mirabilenet_currency(region),
            "resumen": {
                "clientes_activos": count("servicios_activos"),
                "ingresos": self._mirabilenet_sum(domains, "pagos_periodo", "amount"),
                "servicios_total": count("servicios_total"),
                "cartera_vencida": self._mirabilenet_sum(domains, "cartera_vencida",
                                                         "amount_residual"),
            },
            "ingresos_gastos": self._mirabilenet_income_expense(region, today),
            "servicios_estado": self._mirabilenet_service_states(domains),
            "actividad": self._mirabilenet_activity(domains),
            "puesta_en_marcha": self._mirabilenet_setup(domains),
            "cobranza_diaria": self._mirabilenet_daily(domains, period, today),
            "cobranza_metodo": self._mirabilenet_methods(domains),
            "clientes": {key: count(key) for key in (
                "clientes_nuevos_hoy", "clientes_nuevos_mes", "clientes_total",
                "clientes_prospectos", "clientes_instalacion", "clientes_activos",
                "clientes_morosos", "clientes_suspendidos", "clientes_bajas")},
            "cobros": self._mirabilenet_collections(domains),
            "red": self._mirabilenet_network(domains),
            "capacidad": self._mirabilenet_capacity(domains),
            "soporte": {
                "averias_abiertas": count("averias_abiertas"),
                "casos_abiertos": count("casos_abiertos"),
                "instalaciones_pendientes": count("instalaciones_pendientes"),
            },
            "cartera": self._mirabilenet_overdue(domains, today),
            "ultimos_pagos": self._mirabilenet_last_payments(domains),
        }

    @api.model
    def _mirabilenet_currency(self, region):
        """La moneda de las regiones (bolivianos), no la de la compañía."""
        region = region or self.env.user.mirabilenet_region_id or             self.env["mirabilenet.region"].search([], limit=1)
        currency = region.currency_id or self.env.company.currency_id
        return currency.symbol or currency.name or ""

    @api.model
    def _mirabilenet_service_states(self, domains):
        model, domain, _title = domains["servicios_total"]
        if not self._mirabilenet_can(model):
            return None
        counts = dict(self.env[model]._read_group(domain, ["state"], ["__count"]))
        return [{"clave": state, "etiqueta": label, "cantidad": counts.get(state, 0)}
                for state, label in self.env[model]._fields["state"].selection]

    @api.model
    def _mirabilenet_income_expense(self, region, today):
        Payment, Move = self.env["account.payment"], self.env["account.move"]
        if not self._mirabilenet_can("account.payment"):
            return None
        months = periodos.meses_atras(today, 6)
        start, end = months[0][0], months[-1][1]
        inbound = self._mirabilenet_scope("account.payment", [
            ("payment_type", "=", "inbound"), ("state", "in", PAYMENT_STATES),
            ("date", ">=", start), ("date", "<=", end)], region)
        income = {m.replace(day=1): total for m, total in Payment._read_group(
            inbound, ["date:month"], ["amount:sum"])}
        expenses, has_expenses = {}, False
        if self._mirabilenet_can("account.move"):
            bills = self._mirabilenet_scope("account.move", [
                ("move_type", "=", "in_invoice"), ("state", "=", "posted"),
                ("invoice_date", ">=", start), ("invoice_date", "<=", end)], region)
            expenses = {m.replace(day=1): total for m, total in Move._read_group(
                bills, ["invoice_date:month"], ["amount_total_signed:sum"])}
            has_expenses = bool(expenses)
        rows = []
        for first, _last, label in months:
            rows.append({"etiqueta": label, "ingresos": income.get(first, 0.0),
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
    def _mirabilenet_daily(self, domains, period, today):
        model, domain, _title = domains["pagos_mes"]
        if not self._mirabilenet_can(model):
            return None
        # La cobranza diaria muestra siempre 30 días: con «hoy» un solo punto no dice nada.
        start, end = periodos.rango("30" if period in ("hoy", "7") else period, today)
        domain = [d for d in domain if not (isinstance(d, tuple) and d[0] == "date")]
        domain += [("date", ">=", start), ("date", "<=", end)]
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
        proofs = self._mirabilenet_count(domains, "comprobantes_revision")
        return {
            "hoy": self._mirabilenet_sum(domains, "pagos_hoy", "amount"),
            "mes": self._mirabilenet_sum(domains, "pagos_mes", "amount"),
            "por_aprobar": proofs,
            "recibos_hoy": self._mirabilenet_count(domains, "pagos_hoy"),
            "vencido": self._mirabilenet_sum(domains, "cartera_vencida", "amount_residual"),
            "vence_7": self._mirabilenet_sum(domains, "vence_7", "amount_residual"),
        }

    @api.model
    def _mirabilenet_network(self, domains):
        count = lambda key: self._mirabilenet_count(domains, key)  # noqa: E731
        return {
            "routers_total": count("routers_total"),
            "routers_conectados": count("routers_conectados"),
            "pppoe_total": count("pppoe_total"),
            "pppoe_desincronizadas": count("pppoe_desincronizadas"),
            # Todavía no se leen del router: se dice, no se pone 0.
            "sesiones_en_linea": None,
            "trafico": None,
        }

    @api.model
    def _mirabilenet_capacity(self, domains):
        model, domain, _title = domains["nodos"]
        installed = None
        if self._mirabilenet_can(model):
            installed = sum(self.env[model].search(domain).mapped("capacidad_instalada")) or None
        used_domain = domains["servicios_total"][1] + [("state", "in", OPEN_SERVICE_STATES)]
        used = (self.env["mirabilenet.service"].search_count(used_domain)
                if self._mirabilenet_can("mirabilenet.service") else None)
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
    def _mirabilenet_overdue(self, domains, today):
        model, domain, _title = domains["cartera_vencida"]
        if not self._mirabilenet_can(model):
            return None
        rows = []
        for partner, total, oldest in self.env[model]._read_group(
                domain, ["partner_id"], ["amount_residual:sum", "invoice_date_due:min"],
                order="amount_residual:sum desc", limit=OVERDUE_LIMIT):
            rows.append({"cliente": partner.display_name, "monto": total,
                         "dias": (today - oldest).days if oldest else None})
        return {"total": self._mirabilenet_sum(domains, "cartera_vencida", "amount_residual"),
                "clientes": rows}

    @api.model
    def _mirabilenet_last_payments(self, domains):
        model, domain, _title = domains["pagos_mes"]
        if not self._mirabilenet_can(model):
            return None
        domain = [d for d in domain if not (isinstance(d, tuple) and d[0] == "date")]
        payments = self.env[model].search(domain, order="date desc, id desc",
                                          limit=LAST_PAYMENTS_LIMIT)
        return [{"id": p.id, "cliente": p.partner_id.display_name or "",
                 "monto": p.amount, "fecha": fields.Date.to_string(p.date),
                 "metodo": p.journal_id.name or "", "referencia": p.name or ""}
                for p in payments]

    # -- Abrir la lista de una tarjeta ---------------------------------------------
    @api.model
    def action_open(self, key, period="30", region_id=False):
        region = self._mirabilenet_region(region_id)
        domains = self._mirabilenet_domains(periodos.periodo_valido(period), region)
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
