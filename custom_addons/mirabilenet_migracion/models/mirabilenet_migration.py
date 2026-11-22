"""Migración del sistema anterior a Odoo, por etapas, repetible y con informe de control.

Reglas (fase 9 de la guía):
- Cada registro migrado guarda el identificador que tenía (ir.model.data, módulo «migracion»).
- Ejecutarlo dos veces no duplica: lo ya migrado se salta.
- Nada se rellena para que «entre»: lo que no cumple una regla queda rechazado con su motivo.
- Las contraseñas no se migran.
- Si una suma de control no coincide, se detiene y muestra la diferencia.

Etapas de inventario, mensajería, contenido web, AeroLab y pasantías.

Los archivos (comprobantes, imágenes, QR, entregas) no están en la base del sistema anterior:
se leen de la copia de sus carpetas `media` y `private_media`, que se indican al correr la
migración. Sin ellas, lo que necesita un archivo se rechaza con su motivo.
"""
import base64
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytz
from markupsafe import Markup, escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError

XMLID_MODULE = "migracion"
#: Roles de clientes del portal anterior: no son personal y no pasan como usuarios internos.
CUSTOMER_ROLES = {"cliente_emp_admin", "cliente_emp_visor", "cliente_residencial"}
#: Avisos que cuentan como deuda en el sistema anterior.
OPEN_CHARGE_STATES = ("emitido", "pendiente", "pago_parcial", "vencido")
#: Avisos que no pasan: no son deuda ni historia de cobro.
SKIPPED_CHARGE_STATES = {"borrador": "borrador sin emitir", "anulado": "anulado",
                         "en_revision": "en revisión: resolverlo antes de migrar",
                         "incobrable": "incobrable: decidir antes de migrar"}
CASH_METHODS = ("efectivo",)
DEFAULT_TZ = "America/La_Paz"
INTERN_STAGE = {"pendiente": "stage_todo", "en_curso": "stage_doing", "cambios": "stage_doing",
                "entregada": "stage_delivered", "aprobada": "stage_approved"}
INTERN_STATE = {"cambios": "02_changes_requested", "aprobada": "03_approved"}
REPORT_FIELDS = {"objetivo": "goal", "resumen": "summary", "actividades": "procedure",
                 "herramientas": "tools", "parametros": "parameters", "resultados": "results",
                 "validacion": "validation", "justificacion": "rationale",
                 "dificultades": "difficulties", "proximos_pasos": "next_steps",
                 "referencias": "references"}
ENROLLMENT_STATE = {"nueva": "draft", "preinscrita": "draft", "espera": "draft",
                    "confirmada": "open", "cancelada": "cancel"}


def hours(value):
    return value.hour + value.minute / 60.0 if isinstance(value, time) else 0.0


class MigrationMismatch(UserError):
    pass


class Stage:
    """Lo que pasó en una etapa: el informe de control la imprime tal cual."""

    def __init__(self, name, source_count):
        self.name = name
        self.source = source_count
        self.created = 0
        self.existing = 0
        self.rejected = []
        self.notes = []

    def reject(self, table, old_id, reason):
        self.rejected.append((table, old_id, reason))

    def as_dict(self):
        return {"etapa": self.name, "origen": self.source, "migrados": self.created,
                "ya_migrados": self.existing, "rechazados": self.rejected, "notas": self.notes}


class MirabilenetMigration(models.AbstractModel):
    _name = "mirabilenet.migration"
    _description = "MIRABILENET: migración del sistema anterior"

    # -- identificadores del origen ------------------------------------------
    def _xmlid(self, table, old_id):
        return "%s_%s" % (table, old_id)

    def _ref(self, model, table, old_id):
        if not old_id:
            return self.env[model]
        data = self.env["ir.model.data"].sudo().search(
            [("module", "=", XMLID_MODULE), ("name", "=", self._xmlid(table, old_id))], limit=1)
        return self.env[model].browse(data.res_id) if data else self.env[model]

    def _bind(self, table, old_id, record):
        self.env["ir.model.data"].sudo().create({
            "module": XMLID_MODULE, "name": self._xmlid(table, old_id), "model": record._name,
            "res_id": record.id, "noupdate": True})

    def _each(self, stage, table, model, rows, build):
        """Crea lo que falta; lo ya migrado se salta; lo que no cumple, se rechaza."""
        Model = self.env[model]
        for row in rows:
            if self._ref(model, table, row["id"]):
                stage.existing += 1
                continue
            try:
                with self.env.cr.savepoint():
                    vals = build(row)
                    if isinstance(vals, str):
                        stage.reject(table, row["id"], vals)
                        continue
                    record = Model.create(vals)
                    self._bind(table, row["id"], record)
                    stage.created += 1
            except Exception as exc:  # pylint: disable=broad-except
                stage.reject(table, row["id"], str(exc).splitlines()[0][:200])

    # -- etapas ---------------------------------------------------------------
    def _stage_organization(self, src):
        stages = []
        Currency = self.env["res.currency"].with_context(active_test=False)
        rows = src.rows("core_region", [
            "code", "name", "wg_region_id", "active", "dia_emision", "dia_vencimiento",
            "dia_emision_prepago", "prorrateo_prepago_activacion", "prorrateo_prepago_desde",
            "dias_gracia", "hora_corte", "suspension_automatica", "reactivacion_automatica",
            "moneda", "objetivo_mrr", "precio_referencia"])
        stage = Stage("Regiones", len(rows))

        def region(row):
            currency = Currency.search([("name", "=", row["moneda"])], limit=1)
            if not currency:
                return "moneda %s no existe en Odoo" % row["moneda"]
            if not currency.active:
                currency.active = True
            cut = row["hora_corte"] or time(9)
            return {"code": row["code"], "name": row["name"],
                    "wg_region_id": row["wg_region_id"], "active": row["active"],
                    "dia_emision": row["dia_emision"], "dia_vencimiento": row["dia_vencimiento"],
                    "dia_emision_prepago": row["dia_emision_prepago"],
                    "prorrateo_prepago_activacion": row["prorrateo_prepago_activacion"],
                    "prorrateo_prepago_desde": row["prorrateo_prepago_desde"],
                    "dias_gracia": row["dias_gracia"],
                    "hora_corte": cut.hour + cut.minute / 60.0,
                    "suspension_automatica": row["suspension_automatica"],
                    "reactivacion_automatica": row["reactivacion_automatica"],
                    "currency_id": currency.id, "objetivo_mrr": row["objetivo_mrr"] or 0,
                    "precio_referencia": row["precio_referencia"] or 0}
        self._each(stage, "core_region", "mirabilenet.region", rows, region)
        stages.append(stage)

        def child(table, model, label, columns, build):
            rows = src.rows(table, columns)
            stage = Stage(label, len(rows))
            self._each(stage, table, model, rows, build)
            stages.append(stage)

        def need(model, table, old_id, what):
            record = self._ref(model, table, old_id)
            return record, (None if record else "%s %s sin migrar" % (what, old_id))

        def branch(row):
            region, error = need("mirabilenet.region", "core_region", row["region_id"], "región")
            return error or {"region_id": region.id, "code": row["code"], "name": row["name"],
                             "address": row["address"] or False, "phone": row["phone"] or False,
                             "active": row["active"]}

        def zone(row):
            region, error = need("mirabilenet.region", "core_region", row["region_id"], "región")
            return error or {"region_id": region.id, "code": row["code"], "name": row["name"],
                             "sector": row["sector"] or False, "active": row["active"]}

        def node(row):
            zone_rec, error = need("mirabilenet.zone", "core_zone", row["zone_id"], "zona")
            return error or {"zone_id": zone_rec.id, "region_id": zone_rec.region_id.id,
                             "code": row["code"], "name": row["name"],
                             "latitude": float(row["latitude"] or 0),
                             "longitude": float(row["longitude"] or 0),
                             "capacidad_instalada": row["capacidad_instalada"],
                             "active": row["active"]}

        child("core_branch", "mirabilenet.branch", "Sucursales",
              ["region_id", "code", "name", "address", "phone", "active"], branch)
        child("core_zone", "mirabilenet.zone", "Zonas",
              ["region_id", "code", "name", "sector", "active"], zone)
        child("core_node", "mirabilenet.node", "Nodos",
              ["zone_id", "code", "name", "latitude", "longitude", "capacidad_instalada",
               "active"], node)
        return stages

    def _stage_users(self, src):
        rows = src.rows("core_user", ["username", "first_name", "last_name", "email",
                                      "is_active", "role", "region_id", "branch_id"])
        stage = Stage("Usuarios", len(rows))
        roles = dict(self.env["res.users"]._fields["mirabilenet_role"].selection)
        Users = self.env["res.users"].with_context(no_reset_password=True)

        def user(row):
            if row["role"] in CUSTOMER_ROLES:
                return "rol de cliente del portal (%s): no es personal" % row["role"]
            if row["role"] not in roles:
                return "rol desconocido: %s" % row["role"]
            if Users.with_context(active_test=False).search_count(
                    [("login", "=", row["username"])]):
                return "ya existe un usuario con el login %s" % row["username"]
            name = " ".join(p for p in (row["first_name"], row["last_name"]) if p) \
                or row["username"]
            return {"login": row["username"], "name": name, "email": row["email"] or False,
                    "active": row["is_active"], "mirabilenet_role": row["role"],
                    "mirabilenet_region_id": self._ref(
                        "mirabilenet.region", "core_region", row["region_id"]).id,
                    "mirabilenet_branch_id": self._ref(
                        "mirabilenet.branch", "core_branch", row["branch_id"]).id}
        # La contraseña no se migra: cada persona define una nueva al entrar.
        self.with_context(active_test=False)._each(stage, "core_user", "res.users", rows, user)
        stage.notes.append(_("Sin contraseña: enviar a cada usuario el enlace para definirla."))
        return [stage]

    def _stage_customers(self, src):
        rows = src.rows("crm_customer", [
            "code", "tipo", "nombre", "documento", "telefono", "whatsapp", "email", "direccion",
            "region_id", "zone_id", "branch_id", "estado", "vendedor_id", "contacto_verificado",
            "notas", "requiere_factura", "nit_facturacion", "razon_social_facturacion",
            "complemento_documento"])
        stage = Stage("Clientes", len(rows))
        Partner = self.env["res.partner"]
        siat = "mira_siat_legal_name" in Partner._fields

        def customer(row):
            region = self._ref("mirabilenet.region", "core_region", row["region_id"])
            if not region:
                return "región %s sin migrar" % row["region_id"]
            vals = {"name": row["nombre"], "mirabilenet_is_customer": True,
                    "mirabilenet_code": row["code"], "mirabilenet_customer_type": row["tipo"],
                    "mirabilenet_region_id": region.id,
                    "mirabilenet_zone_id": self._ref("mirabilenet.zone", "core_zone",
                                                     row["zone_id"]).id,
                    "mirabilenet_branch_id": self._ref("mirabilenet.branch", "core_branch",
                                                       row["branch_id"]).id,
                    "mirabilenet_state": row["estado"], "phone": row["telefono"] or False,
                    "mirabilenet_whatsapp": row["whatsapp"] or False,
                    "email": row["email"] or False, "street": row["direccion"] or False,
                    "mirabilenet_contact_verified": row["contacto_verificado"],
                    "mirabilenet_requires_invoice": row["requiere_factura"],
                    "comment": row["notas"] or False,
                    "user_id": self._ref("res.users", "core_user", row["vendedor_id"]).id,
                    "vat": row["nit_facturacion"] or row["documento"] or False}
            if siat:
                vals.update(mira_siat_legal_name=row["razon_social_facturacion"] or False,
                            mira_siat_complement=row["complemento_documento"] or False)
            return vals
        self._each(stage, "crm_customer", "res.partner", rows, customer)

        contacts = src.rows("crm_customercontact", ["customer_id", "nombre", "cargo", "telefono",
                                                    "email", "autorizado_soporte",
                                                    "autorizado_pagos"])
        contact_stage = Stage("Contactos de clientes", len(contacts))

        def contact(row):
            parent = self._ref("res.partner", "crm_customer", row["customer_id"])
            if not parent:
                return "cliente %s sin migrar" % row["customer_id"]
            return {"parent_id": parent.id, "type": "contact", "name": row["nombre"],
                    "function": row["cargo"] or False, "phone": row["telefono"] or False,
                    "email": row["email"] or False,
                    "mirabilenet_authorized_support": row["autorizado_soporte"],
                    "mirabilenet_authorized_payments": row["autorizado_pagos"]}
        self._each(contact_stage, "crm_customercontact", "res.partner", contacts, contact)
        return [stage, contact_stage]

    def _stage_plans(self, src):
        rows = src.rows("isp_plan", ["region_id", "code", "nombre", "bajada_mbps", "subida_mbps",
                                     "precio", "perfil_ppp", "perfil_reducido", "incluye_tv",
                                     "activo", "publicar_en_web"])
        stage = Stage("Planes", len(rows))

        def plan(row):
            return {"name": row["nombre"], "type": "service", "mirabilenet_is_plan": True,
                    "mirabilenet_plan_code": row["code"],
                    "mirabilenet_region_id": self._ref("mirabilenet.region", "core_region",
                                                       row["region_id"]).id,
                    "mirabilenet_down_mbps": row["bajada_mbps"],
                    "mirabilenet_up_mbps": row["subida_mbps"], "list_price": row["precio"],
                    "mirabilenet_ppp_profile": row["perfil_ppp"] or False,
                    "mirabilenet_reduced_profile": row["perfil_reducido"] or False,
                    "mirabilenet_includes_tv": row["incluye_tv"], "active": row["activo"],
                    "mirabilenet_publish_web": row["publicar_en_web"], "taxes_id": [(5, 0, 0)]}
        self._each(stage, "isp_plan", "product.template", rows, plan)
        return [stage]

    def _stage_network(self, src):
        rows = src.rows("isp_router", [
            "region_id", "zone_id", "node_id", "nombre", "modelo", "tipo_equipo",
            "routeros_version", "funcion", "modo_control", "wg_ip", "wg_public_key", "identity",
            "serial", "board_name", "api_user", "api_port", "api_address_before",
            "lan_networks", "estado", "api_password"])
        stage = Stage("Routers", len(rows))
        no_credentials = 0

        def router(row):
            nonlocal no_credentials
            region = self._ref("mirabilenet.region", "core_region", row["region_id"])
            if not region:
                return "región %s sin migrar" % row["region_id"]
            if row["api_password"]:
                no_credentials += 1
            return {"region_id": region.id, "name": row["nombre"],
                    "zone_id": self._ref("mirabilenet.zone", "core_zone", row["zone_id"]).id,
                    "node_id": self._ref("mirabilenet.node", "core_node", row["node_id"]).id,
                    "model": row["modelo"] or False, "equipment_type": row["tipo_equipo"],
                    "routeros_version": row["routeros_version"] or False,
                    "function": row["funcion"], "control_mode": row["modo_control"],
                    "wg_ip": row["wg_ip"], "wg_public_key": row["wg_public_key"] or False,
                    "identity": row["identity"] or False, "serial": row["serial"] or False,
                    "board_name": row["board_name"] or False,
                    "api_user": row["api_user"] or False, "api_port": row["api_port"],
                    "api_address_before": row["api_address_before"] or False,
                    "lan_networks": row["lan_networks"] or False, "state": row["estado"]}
        self._each(stage, "isp_router", "mirabilenet.router", rows, router)
        if no_credentials:
            stage.notes.append(_(
                "%s routers con contraseña de API cifrada con la clave del sistema anterior: no "
                "se migra. Hay que volver a cargarla en cada router.", no_credentials))

        subnets = src.rows("isp_networksubnet", ["region_id", "site_id", "cidr", "tipo",
                                                 "estado", "customer_id", "descripcion",
                                                 "red_heredada"])
        subnet_stage = Stage("Subredes", len(subnets))

        def subnet(row):
            region = self._ref("mirabilenet.region", "core_region", row["region_id"])
            if not region:
                return "región %s sin migrar" % row["region_id"]
            return {"region_id": region.id, "site_id": row["site_id"], "cidr": row["cidr"],
                    "kind": row["tipo"], "state": row["estado"],
                    "partner_id": self._ref("res.partner", "crm_customer",
                                            row["customer_id"]).id,
                    "description": row["descripcion"] or False,
                    "legacy_network": row["red_heredada"] or False}
        self._each(subnet_stage, "isp_networksubnet", "mirabilenet.subnet", subnets, subnet)
        return [stage, subnet_stage]

    def _stage_services(self, src):
        rows = src.rows("isp_service", [
            "customer_id", "region_id", "node_id", "router_id", "plan_id", "estado",
            "modalidad_pago", "fecha_alta", "fecha_baja", "dia_facturacion", "precio_mensual",
            "direccion_instalacion", "observaciones"])
        stage = Stage("Servicios", len(rows))

        def service(row):
            partner = self._ref("res.partner", "crm_customer", row["customer_id"])
            plan = self._ref("product.template", "isp_plan", row["plan_id"])
            region = self._ref("mirabilenet.region", "core_region", row["region_id"])
            for record, what, old in ((partner, "cliente", row["customer_id"]),
                                      (plan, "plan", row["plan_id"]),
                                      (region, "región", row["region_id"])):
                if not record:
                    return "%s %s sin migrar" % (what, old)
            return {"partner_id": partner.id, "plan_id": plan.id, "region_id": region.id,
                    "node_id": self._ref("mirabilenet.node", "core_node", row["node_id"]).id,
                    "router_id": self._ref("mirabilenet.router", "isp_router",
                                           row["router_id"]).id,
                    "state": row["estado"], "payment_mode": row["modalidad_pago"],
                    "date_start": row["fecha_alta"], "date_end": row["fecha_baja"],
                    "billing_day": row["dia_facturacion"],
                    "monthly_price": row["precio_mensual"],
                    "install_address": row["direccion_instalacion"] or False,
                    "notes": row["observaciones"] or False}
        self._each(stage, "isp_service", "mirabilenet.service", rows, service)

        accounts = src.rows("isp_pppoeaccount", ["service_id", "username", "ip_fija", "perfil",
                                                 "caller_id", "habilitado", "password"])
        account_stage = Stage("Cuentas PPPoE", len(accounts))
        encrypted = 0

        def account(row):
            nonlocal encrypted
            service = self._ref("mirabilenet.service", "isp_service", row["service_id"])
            if not service:
                return "servicio %s sin migrar" % row["service_id"]
            if row["password"]:
                encrypted += 1
            return {"service_id": service.id, "username": row["username"],
                    "fixed_ip": row["ip_fija"] or False, "profile": row["perfil"] or False,
                    "caller_id": row["caller_id"] or False, "enabled": row["habilitado"],
                    "synced": False}
        self._each(account_stage, "isp_pppoeaccount", "mirabilenet.pppoe.account", accounts,
                   account)
        if encrypted:
            account_stage.notes.append(_(
                "%s contraseñas PPPoE cifradas con la clave del sistema anterior: no se migran. "
                "Siguen funcionando en los routers; se recargan en Odoo al cambiarlas.", encrypted))
        return [stage, account_stage]

    def _stage_billing(self, src):
        rows = src.rows("billing_charge", [
            "numero", "customer_id", "service_id", "region_id", "concepto", "fecha_emision",
            "fecha_vencimiento", "monto_total", "saldo", "estado"])
        stage = Stage("Avisos de cobro → facturas", len(rows))
        Move = self.env["account.move"].with_context(mirabilenet_migration=True)
        fallback = self._migration_product()

        def charge(row):
            if row["estado"] in SKIPPED_CHARGE_STATES:
                return "aviso %s: %s" % (row["numero"], SKIPPED_CHARGE_STATES[row["estado"]])
            partner = self._ref("res.partner", "crm_customer", row["customer_id"])
            if not partner:
                return "cliente %s sin migrar" % row["customer_id"]
            service = self._ref("mirabilenet.service", "isp_service", row["service_id"])
            region = self._ref("mirabilenet.region", "core_region", row["region_id"])
            product = service.plan_id.product_variant_id or fallback
            return {"move_type": "out_invoice", "partner_id": partner.id,
                    "invoice_date": row["fecha_emision"],
                    "invoice_date_due": row["fecha_vencimiento"],
                    "ref": row["numero"], "mirabilenet_service_id": service.id,
                    "mirabilenet_region_id": region.id, "currency_id": region.currency_id.id,
                    "invoice_line_ids": [(0, 0, {
                        "product_id": product.id, "name": row["concepto"] or row["numero"],
                        "quantity": 1, "price_unit": row["monto_total"],
                        "tax_ids": [(5, 0, 0)]})]}
        rows_by_id = {row["id"]: row for row in rows}
        Model = self.env["account.move"]
        for row in rows:
            if self._ref("account.move", "billing_charge", row["id"]):
                stage.existing += 1
                continue
            vals = charge(row)
            if isinstance(vals, str):
                stage.reject("billing_charge", row["id"], vals)
                continue
            try:
                with self.env.cr.savepoint():
                    move = Move.create(vals)
                    move.action_post()
                    self._bind("billing_charge", row["id"], move)
                    stage.created += 1
            except Exception as exc:  # pylint: disable=broad-except
                stage.reject("billing_charge", row["id"], str(exc).splitlines()[0][:200])

        # Pagos aprobados, aplicados a sus avisos tal como estaban en el origen.
        payments = src.rows("billing_payment", ["customer_id", "region_id", "monto", "metodo",
                                                "referencia", "fecha_pago", "estado"],
                            where="estado = 'aprobado'")
        allocations = defaultdict(list)
        for alloc in src.rows("billing_paymentallocation", ["payment_id", "charge_id", "monto"]):
            allocations[alloc["payment_id"]].append(alloc)
        receipts = {}
        for receipt in src.rows("billing_receipt", ["payment_id", "numero", "anulado",
                                                    "anula_a_id"]):
            if not receipt["anulado"] and not receipt["anula_a_id"]:
                receipts[receipt["payment_id"]] = receipt["numero"]
        pay_stage = Stage("Pagos y aplicaciones", len(payments))
        for row in payments:
            if self._ref("account.payment", "billing_payment", row["id"]):
                pay_stage.existing += 1
                continue
            partner = self._ref("res.partner", "crm_customer", row["customer_id"])
            if not partner:
                pay_stage.reject("billing_payment", row["id"],
                                 "cliente %s sin migrar" % row["customer_id"])
                continue
            try:
                with self.env.cr.savepoint():
                    created = self._migrate_payment(row, partner, allocations[row["id"]],
                                                    receipts.get(row["id"]), rows_by_id)
                    self._bind("billing_payment", row["id"], created[0])
                    for extra_index, extra in enumerate(created[1:], start=1):
                        self._bind("billing_payment", "%s_%d" % (row["id"], extra_index),
                                   extra)
                    pay_stage.created += 1
            except Exception as exc:  # pylint: disable=broad-except
                pay_stage.reject("billing_payment", row["id"], str(exc).splitlines()[0][:200])
        pay_stage.notes.append(_(
            "El número de recibo del sistema anterior queda en la referencia del pago. Odoo "
            "numera los pagos nuevos con su propia secuencia: no hay cajas con correlativo."))
        return [stage, pay_stage]

    def _stage_contracts(self, src):
        """Cada servicio vigente recibe su contrato de cobro, que empieza a facturar en la
        fecha de cambio. Lo anterior ya está en las facturas migradas."""
        start = self.env.context.get("mirabilenet_billing_start")
        services = self.env["mirabilenet.service"].browse(
            self._migrated_ids("mirabilenet.service", "isp_service")).filtered(
            lambda s: s.state in ("activo", "moroso", "suspendido"))
        stage = Stage("Contratos de cobro", len(services))
        if not start:
            stage.notes.append(_("Sin fecha de inicio del cobro en Odoo: no se crean contratos. "
                                 "Indíquela con MIRABILENET_INICIO_COBRO."))
            return [stage]
        for service in services:
            if service.contract_id:
                stage.existing += 1
                continue
            try:
                with self.env.cr.savepoint():
                    service._mirabilenet_ensure_contract(fields.Date.to_date(start))
                    stage.created += 1
            except Exception as exc:  # pylint: disable=broad-except
                stage.reject("isp_service", service.id, str(exc).splitlines()[0][:200])
        return [stage]

    def _migration_product(self):
        product = self.env.ref("mirabilenet_migracion.product_migrated_charge",
                               raise_if_not_found=False)
        return product

    def _migrate_payment(self, row, partner, allocations, receipt_number, charges):
        """Un pago del origen: una parte por cada aviso al que se aplicó, y lo que sobró queda
        como pago sin aplicar (crédito del cliente)."""
        journal = self._journal("cash" if row["metodo"] in CASH_METHODS else "bank")
        memo = " / ".join(p for p in (receipt_number and "Recibo %s" % receipt_number,
                                      row["referencia"]) if p) or "Pago migrado"
        date = self._local_date(row["fecha_pago"])
        created = self.env["account.payment"]
        applied = Decimal("0")
        for alloc in allocations:
            invoice = self._ref("account.move", "billing_charge", alloc["charge_id"])
            if not invoice:
                raise UserError(_("Aplicado a un aviso que no se migró (%s).",
                                  alloc["charge_id"]))
            wizard = self.env["account.payment.register"].with_context(
                active_model="account.move", active_ids=invoice.ids,
                mirabilenet_migration=True).create({
                    "amount": alloc["monto"], "payment_date": date, "journal_id": journal.id,
                    "communication": memo})
            created |= wizard._create_payments()
            applied += Decimal(alloc["monto"])
        rest = Decimal(row["monto"]) - applied
        if rest > 0:
            payment = self.env["account.payment"].create({
                "payment_type": "inbound", "partner_type": "customer", "partner_id": partner.id,
                "amount": rest, "date": date, "journal_id": journal.id, "memo": memo})
            payment.action_post()
            created |= payment
        if not created:
            raise UserError(_("Pago sin monto."))
        return created

    def _tz(self):
        return self.env["ir.config_parameter"].sudo().get_param("mirabilenet.timezone",
                                                                DEFAULT_TZ)

    def _local_date(self, moment):
        """La fecha de un instante en la hora de Bolivia (la misma que usa el control)."""
        if not moment:
            return False
        if moment.tzinfo is None:
            moment = pytz.utc.localize(moment)
        return moment.astimezone(pytz.timezone(self._tz())).date()

    def _journal(self, kind):
        journal = self.env["account.journal"].search(
            [("type", "=", kind), ("company_id", "=", self.env.company.id)], limit=1)
        if not journal:
            raise UserError(_("Falta un diario de tipo %s en la empresa.", kind))
        return journal

    # -- sumas de control ----------------------------------------------------
    def _ran(self, stage):
        return stage in (self.env.context.get("mirabilenet_stages") or ())

    def _controls(self, src):
        """Las sumas que tienen que dar igual en los dos sistemas, de las etapas que corrieron."""
        checks = []
        if self._ran("billing"):
            checks += self._billing_controls(src)
        if self._ran("services"):
            checks += self._service_controls(src)
        if self._ran("inventory"):
            source_qty = Decimal(src.scalar(
                "SELECT COALESCE(SUM(cantidad), 0) FROM {schema}.inventory_inventorystock"))
            locations = self.env["stock.warehouse"].browse(
                self._migrated_ids("stock.warehouse", "inventory_warehouse")).mapped(
                "lot_stock_id")
            quants = self.env["stock.quant"].search([("location_id", "child_of", locations.ids)]) \
                if locations else self.env["stock.quant"]
            checks.append(("Unidades en almacenes", source_qty,
                           Decimal(str(sum(quants.mapped("quantity"))))))
        if self._ran("messaging"):
            src.cr.execute("SELECT estado, COUNT(*) FROM %s.messaging_whatsappproof "
                           "GROUP BY 1" % src.schema)
            source = dict(src.cr.fetchall())
            proofs = self.env["mirabilenet.whatsapp.proof"].browse(
                self._migrated_ids("mirabilenet.whatsapp.proof", "messaging_whatsappproof"))
            odoo = Counter(proofs.mapped("state"))
            for state in sorted(set(source) | set(odoo)):
                checks.append(("Comprobantes %s" % state, Decimal(source.get(state, 0)),
                               Decimal(odoo.get(state, 0))))
        return checks

    def _billing_controls(self, src):
        source_due = Decimal(src.scalar(
            "SELECT COALESCE(SUM(saldo), 0) FROM {schema}.billing_charge WHERE estado IN %s",
            [OPEN_CHARGE_STATES]))
        invoices = self.env["account.move"].search([
            ("id", "in", self._migrated_ids("account.move", "billing_charge"))])
        odoo_due = Decimal(str(round(sum(invoices.mapped("amount_residual")), 2)))
        checks = [("Saldo total adeudado", source_due, odoo_due)]

        src.cr.execute(
            "SELECT to_char(fecha_pago AT TIME ZONE %%s, 'YYYY-MM'), SUM(monto) "
            "FROM %s.billing_payment WHERE estado = 'aprobado' GROUP BY 1" % src.schema,
            [self._tz()])
        source_months = {month: Decimal(total) for month, total in src.cr.fetchall()}
        payments = self.env["account.payment"].search([
            ("id", "in", self._migrated_ids("account.payment", "billing_payment"))])
        odoo_months = Counter()
        for payment in payments:
            odoo_months[payment.date.strftime("%Y-%m")] += Decimal(str(payment.amount))
        for month in sorted(set(source_months) | set(odoo_months)):
            checks.append(("Cobrado en %s" % month, source_months.get(month, Decimal(0)),
                           odoo_months.get(month, Decimal(0))))
        return checks

    def _service_controls(self, src):
        checks = []
        src.cr.execute("SELECT estado, COUNT(*) FROM %s.isp_service GROUP BY 1" % src.schema)
        source_states = dict(src.cr.fetchall())
        services = self.env["mirabilenet.service"].search([
            ("id", "in", self._migrated_ids("mirabilenet.service", "isp_service"))])
        odoo_states = Counter(services.mapped("state"))
        for state in sorted(set(source_states) | set(odoo_states)):
            checks.append(("Servicios %s" % state, Decimal(source_states.get(state, 0)),
                           Decimal(odoo_states.get(state, 0))))
        return checks

    def _migrated_ids(self, model, table):
        data = self.env["ir.model.data"].sudo().search(
            [("module", "=", XMLID_MODULE), ("model", "=", model),
             ("name", "=like", "%s\\_%%" % table)])
        return data.mapped("res_id")

    # -- ejecución -------------------------------------------------------------
    STAGES = ("organization", "users", "customers", "plans", "network", "services", "billing",
              "inventory", "messaging", "web", "aerolab", "internships", "contracts")

    @api.model
    def _run(self, src, stages=None, check=True):
        """Corre las etapas en orden. Devuelve el informe; con `check`, se detiene si una suma
        de control no coincide."""
        if not self.env.su:
            raise UserError(_("La migración corre como sistema, desde la consola de Odoo."))
        stages = tuple(stages or self.STAGES)
        self = self.with_context(mirabilenet_migration=True, tracking_disable=True,
                                 mail_create_nolog=True, mail_notrack=True,
                                 mirabilenet_stages=stages)
        report = []
        for name in stages:
            for stage in getattr(self, "_stage_%s" % name)(src):
                report.append(stage.as_dict())
        controls = self._controls(src) if check else []
        result = {"etapas": report, "controles": [
            {"control": label, "origen": str(source), "odoo": str(odoo),
             "coincide": source == odoo} for label, source, odoo in controls]}
        bad = [c for c in result["controles"] if not c["coincide"]]
        if bad:
            rejected = ["- %s · %s %s: %s" % (s["etapa"], t, i, r)
                        for s in report for t, i, r in s["rechazados"]]
            raise MigrationMismatch(_(
                "Las sumas de control no coinciden:\n%(bad)s\n\nRechazados:\n%(rej)s",
                bad="\n".join("- %(control)s: origen %(origen)s, Odoo %(odoo)s" % c
                              for c in bad), rej="\n".join(rejected) or "-"))
        return result

    @api.model
    def _report_markdown(self, result):
        lines = ["# Informe de migración", "", "| Etapa | Origen | Migrados | Ya estaban | "
                 "Rechazados |", "|---|---|---|---|---|"]
        for stage in result["etapas"]:
            lines.append("| %s | %s | %s | %s | %s |" % (
                stage["etapa"], stage["origen"], stage["migrados"], stage["ya_migrados"],
                len(stage["rechazados"])))
        lines += ["", "## Sumas de control", "", "| Control | Origen | Odoo | Coincide |",
                  "|---|---|---|---|"]
        lines += ["| %s | %s | %s | %s |" % (c["control"], c["origen"], c["odoo"],
                                              "sí" if c["coincide"] else "**NO**")
                  for c in result["controles"]]
        lines += ["", "## Rechazados y notas", ""]
        for stage in result["etapas"]:
            for table, old_id, reason in stage["rechazados"]:
                lines.append("- %s · %s %s: %s" % (stage["etapa"], table, old_id, reason))
            for note in stage["notas"]:
                lines.append("- %s: %s" % (stage["etapa"], note))
        return "\n".join(lines) + "\n"

    # -- archivos ------------------------------------------------------------
    def _file(self, path, private=False):
        """El archivo de la copia de `media` o `private_media`, en base64; None si no está."""
        root = self.env.context.get(
            "mirabilenet_private_root" if private else "mirabilenet_media_root")
        if not path or not root:
            return None
        full = os.path.realpath(os.path.join(root, path))
        if not full.startswith(os.path.realpath(root) + os.sep) or not os.path.isfile(full):
            return None
        with open(full, "rb") as handle:
            return base64.b64encode(handle.read())

    def _r(self, model, table, old_id):
        return self._ref(model, table, old_id)

    # -- inventario ------------------------------------------------------------
    def _stage_inventory(self, src):
        stages = []
        rows = src.rows("inventory_warehouse", ["branch_id", "code", "nombre", "responsable_id",
                                                "activo"])
        stage = Stage("Almacenes", len(rows))

        def warehouse(row):
            branch = self._r("mirabilenet.branch", "core_branch", row["branch_id"])
            if not branch:
                return "sucursal %s sin migrar" % row["branch_id"]
            if len(row["code"]) > 5:
                return "código %s: Odoo admite hasta 5 caracteres" % row["code"]
            return {"name": row["nombre"], "code": row["code"],
                    "mirabilenet_branch_id": branch.id,
                    "mirabilenet_responsible_id": self._r("res.users", "core_user",
                                                          row["responsable_id"]).id,
                    "active": row["activo"]}
        self._each(stage, "inventory_warehouse", "stock.warehouse", rows, warehouse)
        stages.append(stage)

        rows = src.rows("inventory_inventoryitem", [
            "sku", "categoria", "marca", "modelo", "descripcion", "serializado", "unidad",
            "costo", "precio_venta", "stock_minimo", "activo"])
        stage = Stage("Artículos de inventario", len(rows))

        def item(row):
            category = self.env.ref("mirabilenet_inventario.category_%s" % row["categoria"],
                                    raise_if_not_found=False)
            if not category:
                return "categoría desconocida: %s" % row["categoria"]
            service = row["categoria"] == "servicio"
            name = row["descripcion"] or " ".join(p for p in (row["marca"], row["modelo"]) if p)
            return {"name": name or row["sku"], "default_code": row["sku"],
                    "type": "service" if service else "consu", "is_storable": not service,
                    "tracking": "serial" if row["serializado"] and not service else "none",
                    "categ_id": category.id, "mirabilenet_brand": row["marca"] or False,
                    "mirabilenet_model": row["modelo"] or False,
                    "standard_price": row["costo"], "list_price": row["precio_venta"],
                    "mirabilenet_stock_min": row["stock_minimo"], "active": row["activo"],
                    "taxes_id": [(5, 0, 0)]}
        self._each(stage, "inventory_inventoryitem", "product.template", rows, item)
        stages.append(stage)

        rows = src.rows("inventory_inventoryserial", [
            "item_id", "serial", "mac", "region_id", "warehouse_id", "tecnico_id", "customer_id",
            "estado", "proveedor", "fecha_compra", "garantia_hasta", "costo"])
        stage = Stage("Series de equipos", len(rows))

        def serial(row):
            product = self._r("product.template", "inventory_inventoryitem", row["item_id"])
            if not product:
                return "artículo %s sin migrar" % row["item_id"]
            return {"name": row["serial"], "product_id": product.product_variant_id.id,
                    "mirabilenet_state": row["estado"],
                    "mirabilenet_region_id": self._r("mirabilenet.region", "core_region",
                                                     row["region_id"]).id,
                    "mirabilenet_warehouse_id": self._r("stock.warehouse", "inventory_warehouse",
                                                        row["warehouse_id"]).id,
                    "mirabilenet_technician_id": self._r("res.users", "core_user",
                                                         row["tecnico_id"]).id,
                    "mirabilenet_partner_id": self._r("res.partner", "crm_customer",
                                                      row["customer_id"]).id,
                    "mirabilenet_mac": row["mac"] or False,
                    "mirabilenet_supplier": row["proveedor"] or False,
                    "mirabilenet_purchase_date": row["fecha_compra"],
                    "mirabilenet_warranty_until": row["garantia_hasta"],
                    "mirabilenet_cost": row["costo"]}
        self._each(stage, "inventory_inventoryserial", "stock.lot", rows, serial)
        stages.append(stage)

        # Existencias: las cantidades por almacén y una unidad por serie en almacén.
        stock_rows = src.rows("inventory_inventorystock", ["item_id", "warehouse_id",
                                                           "cantidad"])
        stage = Stage("Existencias", len(stock_rows))
        Quant = self.env["stock.quant"].with_context(inventory_mode=True)
        for row in stock_rows:
            product = self._r("product.template", "inventory_inventoryitem", row["item_id"])
            warehouse_rec = self._r("stock.warehouse", "inventory_warehouse", row["warehouse_id"])
            if not product or not warehouse_rec:
                stage.reject("inventory_inventorystock", row["id"], "artículo o almacén sin migrar")
                continue
            if self._r("stock.quant", "inventory_inventorystock", row["id"]):
                stage.existing += 1
                continue
            variant = product.product_variant_id
            if variant.tracking == "serial":
                lots = self.env["stock.lot"].search([
                    ("product_id", "=", variant.id),
                    ("mirabilenet_warehouse_id", "=", warehouse_rec.id),
                    ("mirabilenet_state", "=", "en_almacen")])
                plan = [(lot, 1) for lot in lots]
                if Decimal(row["cantidad"]) != len(lots):
                    stage.reject("inventory_inventorystock", row["id"], _(
                        "%(q)s unidades en el origen y %(n)s series en almacén",
                        q=row["cantidad"], n=len(lots)))
                    continue
            else:
                plan = [(self.env["stock.lot"], float(row["cantidad"]))]
            try:
                with self.env.cr.savepoint():
                    first = None
                    for lot, qty in plan:
                        quant = Quant.create({"product_id": variant.id,
                                              "location_id": warehouse_rec.lot_stock_id.id,
                                              "lot_id": lot.id, "inventory_quantity": qty})
                        quant.action_apply_inventory()
                        first = first or quant
                    if first:
                        self._bind("inventory_inventorystock", row["id"], first)
                    stage.created += 1
            except Exception as exc:  # pylint: disable=broad-except
                stage.reject("inventory_inventorystock", row["id"], str(exc).splitlines()[0][:200])
        moves = src.scalar("SELECT COUNT(*) FROM {schema}.inventory_inventorymovement")
        stage.notes.append(_(
            "%s movimientos históricos no se recrean (cambiarían las existencias); quedan en el "
            "sistema anterior para consulta.", moves))
        stages.append(stage)
        return stages

    # -- mensajería ------------------------------------------------------------
    def _stage_messaging(self, src):
        stages = []

        def simple(table, model, label, columns, build):
            rows = src.rows(table, columns)
            stage = Stage(label, len(rows))
            self._each(stage, table, model, rows, build)
            stages.append(stage)
            return stage

        def need(record, what, old):
            return None if record else "%s %s sin migrar" % (what, old)

        def number(row):
            branch = self._r("mirabilenet.branch", "core_branch", row["branch_id"])
            return need(branch, "sucursal", row["branch_id"]) or {
                "branch_id": branch.id, "phone_number_id": row["phone_number_id"],
                "display_number": row["numero_visible"],
                "sender_name": row["nombre_remitente"] or False, "active": row["activo"],
                "shared_global": row["compartido_global"], "mode": row["modo"],
                "verified_at": row["verificado_at"], "meta_platform": row["plataforma_meta"] or False,
                "last_error": row["ultimo_error"] or False}
        simple("messaging_branchwhatsappnumber", "mirabilenet.whatsapp.number",
               "Números de WhatsApp", ["branch_id", "phone_number_id", "numero_visible",
                                       "nombre_remitente", "activo", "compartido_global", "modo",
                                       "verificado_at", "plataforma_meta", "ultimo_error"], number)

        def template(row):
            variables = row["variables"]
            if isinstance(variables, str):
                variables = json.loads(variables or "[]")
            return {"event": row["evento"], "meta_name": row["nombre_meta"],
                    "region_id": self._r("mirabilenet.region", "core_region",
                                         row["region_id"]).id,
                    "language": row["idioma"], "parameter_format": row["parameter_format"],
                    "variables": ", ".join(variables or []),
                    "reference_text": row["texto_referencia"] or False,
                    "qr_header": row["incluir_qr_encabezado"], "active": row["activo"]}
        simple("messaging_messagetemplate", "mirabilenet.whatsapp.template", "Plantillas",
               ["evento", "region_id", "nombre_meta", "idioma", "parameter_format", "variables",
                "texto_referencia", "incluir_qr_encabezado", "activo"], template)

        def optout(row):
            partner = self._r("res.partner", "crm_customer", row["customer_id"])
            return need(partner, "cliente", row["customer_id"]) or {
                "partner_id": partner.id, "reason": row["motivo"] or False,
                "origin": row["origen"] if row["origen"] in ("cliente", "panel") else "panel"}
        simple("messaging_whatsappoptout", "mirabilenet.whatsapp.optout", "Bajas de mensajes",
               ["customer_id", "motivo", "origen"], optout)

        def consent(row):
            partner = self._r("res.partner", "crm_customer", row["customer_id"])
            return need(partner, "cliente", row["customer_id"]) or {
                "partner_id": partner.id, "origin": row["origen"],
                "detail": row["detalle"] or row["origen"], "granted_at": row["otorgado_at"],
                "user_id": self._r("res.users", "core_user", row["registrado_por_id"]).id}
        simple("messaging_whatsappconsentimiento", "mirabilenet.whatsapp.consent",
               "Consentimientos", ["customer_id", "origen", "detalle", "otorgado_at",
                                   "registrado_por_id"], consent)

        def qr(row):
            region = self._r("mirabilenet.region", "core_region", row["region_id"])
            image = self._file(row["image"])
            if not region:
                return "región %s sin migrar" % row["region_id"]
            if not image:
                return "imagen %s no disponible en la copia de media" % row["image"]
            return {"region_id": region.id, "image": image, "active": row["active"],
                    "user_id": self._r("res.users", "core_user", row["uploaded_by_id"]).id}
        simple("messaging_regionalpaymentqr", "mirabilenet.payment.qr", "QR de pago",
               ["region_id", "image", "active", "uploaded_by_id"], qr)

        def conversation(row):
            return {"channel": row["canal"], "contact": row["contacto"],
                    "partner_id": self._r("res.partner", "crm_customer", row["customer_id"]).id,
                    "region_id": self._r("mirabilenet.region", "core_region",
                                         row["region_id"]).id,
                    "number_id": self._r("mirabilenet.whatsapp.number",
                                         "messaging_branchwhatsappnumber",
                                         row["numero_origen_id"]).id,
                    "state": row["estado"],
                    "attended_by": self._r("res.users", "core_user", row["atendida_por_id"]).id,
                    "last_incoming_at": row["ultimo_entrante_at"],
                    "last_outgoing_at": row["ultimo_saliente_at"],
                    "reviewed_at": row["revisada_at"]}
        simple("messaging_conversacion", "mirabilenet.conversation", "Conversaciones",
               ["canal", "contacto", "customer_id", "region_id", "numero_origen_id", "estado",
                "atendida_por_id", "ultimo_entrante_at", "ultimo_saliente_at", "revisada_at"],
               conversation)

        def message(row):
            conv = self._r("mirabilenet.conversation", "messaging_conversacion",
                           row["conversacion_id"])
            data = row["datos"]
            if isinstance(data, str):
                data = json.loads(data or "{}")
            return need(conv, "conversación", row["conversacion_id"]) or {
                "conversation_id": conv.id, "direction": row["direccion"],
                "origin": row["origen"], "kind": row["tipo"], "text": row["texto"] or False,
                "data": data or {}, "external_id": row["id_externo"],
                "unique_key": row["clave_unica"], "state": row["estado"] or False,
                "error_detail": row["error_detalle"] or False, "sent_at": row["enviado_at"]}
        simple("messaging_mensajeconversacion", "mirabilenet.conversation.message",
               "Mensajes de conversaciones",
               ["conversacion_id", "direccion", "origen", "tipo", "texto", "datos", "id_externo",
                "clave_unica", "estado", "error_detalle", "enviado_at"], message)

        def outbound(row):
            partner = self._r("res.partner", "crm_customer", row["customer_id"])
            region = self._r("mirabilenet.region", "core_region", row["region_id"])
            params = row["parametros"]
            if isinstance(params, str):
                params = json.loads(params or "[]")
            return need(partner, "cliente", row["customer_id"]) or need(
                region, "región", row["region_id"]) or {
                "partner_id": partner.id, "region_id": region.id,
                "charge_id": self._r("account.move", "billing_charge", row["charge_id"]).id,
                "number_id": self._r("mirabilenet.whatsapp.number",
                                     "messaging_branchwhatsappnumber",
                                     row["numero_origen_id"]).id,
                "template_id": self._r("mirabilenet.whatsapp.template",
                                       "messaging_messagetemplate", row["template_id"]).id,
                "event": row["evento"], "destination": row["destino"], "parameters": params,
                "header_image_url": row["header_image_url"] or False, "state": row["estado"],
                "attempts": row["intentos"], "wa_message_id": row["wa_message_id"] or False,
                "error_code": row["error_codigo"] or False,
                "error_detail": row["error_detalle"] or False,
                "unique_key": row["clave_unica"], "sent_at": row["enviado_at"],
                "delivered_at": row["entregado_at"], "read_at": row["leido_at"]}
        simple("messaging_whatsappmessage", "mirabilenet.whatsapp.message",
               "Avisos de WhatsApp enviados",
               ["customer_id", "charge_id", "region_id", "numero_origen_id", "template_id",
                "evento", "destino", "parametros", "header_image_url", "estado", "intentos",
                "wa_message_id", "error_codigo", "error_detalle", "clave_unica", "enviado_at",
                "entregado_at", "leido_at"], outbound)

        def proof(row):
            partner = self._r("res.partner", "crm_customer", row["customer_id"])
            content = self._file(row["file"], private=True)
            if not partner:
                return "cliente %s sin migrar" % row["customer_id"]
            if not content:
                return "archivo %s no disponible en la copia de private_media" % row["file"]
            return {"partner_id": partner.id, "file": content,
                    "file_name": os.path.basename(row["file"]), "mime_type": row["mime_type"],
                    "size_bytes": row["size_bytes"],
                    "charge_id": self._r("account.move", "billing_charge", row["charge_id"]).id,
                    "whatsapp_message_id": row["whatsapp_message_id"], "state": row["estado"],
                    "payment_id": self._r("account.payment", "billing_payment",
                                          row["payment_id"]).id,
                    "reject_reason": row["motivo_rechazo"] or False,
                    "simulated": row["simulado"], "reviewed_at": row["revisado_at"],
                    "reviewed_by": self._r("res.users", "core_user", row["revisado_por_id"]).id}
        simple("messaging_whatsappproof", "mirabilenet.whatsapp.proof", "Comprobantes",
               ["customer_id", "charge_id", "file", "mime_type", "size_bytes",
                "whatsapp_message_id", "estado", "payment_id", "motivo_rechazo", "simulado",
                "revisado_at", "revisado_por_id"], proof)

        def case(row):
            partner = self._r("res.partner", "crm_customer", row["customer_id"])
            return need(partner, "cliente", row["customer_id"]) or {
                "partner_id": partner.id, "kind": row["tipo"], "reason": row["motivo"],
                "state": row["estado"],
                "assigned_to": self._r("res.users", "core_user", row["assigned_to_id"]).id,
                "inbound_message_id": row["inbound_message_id"],
                "conversation_id": self._r("mirabilenet.conversation", "messaging_conversacion",
                                           row["conversacion_id"]).id,
                "resolved_at": row["resolved_at"]}
        simple("messaging_whatsappsupportcase", "mirabilenet.support.case", "Solicitudes",
               ["customer_id", "tipo", "motivo", "estado", "assigned_to_id",
                "inbound_message_id", "conversacion_id", "resolved_at"], case)

        def promo(row):
            return {"name": row["nombre"], "offer": row["descripcion"] or False,
                    "conditions": row["condiciones"] or False,
                    "region_id": self._r("mirabilenet.region", "core_region",
                                         row["region_id"]).id,
                    "date_from": row["vigente_desde"], "date_to": row["vigente_hasta"],
                    "active": row["activa"], "sequence": row["orden"]}
        simple("messaging_promocionretencion", "mirabilenet.retention.promo",
               "Promociones de retención", ["nombre", "descripcion", "condiciones", "region_id",
                                            "vigente_desde", "vigente_hasta", "activa", "orden"],
               promo)

        # Ajustes: un solo registro en cada sistema. Los tokens de Meta van cifrados con la
        # clave del sistema anterior y no se migran.
        settings_stage = Stage("Ajustes de mensajería y del asistente", 2)
        for row in src.rows("messaging_whatsappsettings", [
                "activo", "modo_prueba", "exigir_consentimiento", "api_version", "waba_id",
                "app_id", "hora_inicio", "hora_fin", "dias_recordatorio", "reintentos_max",
                "limite_diario_por_cliente", "horas_silencio_tras_agente", "intervalo_mora_dias",
                "max_recordatorios_mora"]):
            record = self.env["mirabilenet.whatsapp.settings"]._load()
            if self._ref(record._name, "messaging_whatsappsettings", row["id"]):
                settings_stage.existing += 1
                continue
            self._bind("messaging_whatsappsettings", row["id"], record)
            record.write({
                "active_messaging": False, "test_mode": row["modo_prueba"],
                "require_consent": row["exigir_consentimiento"],
                "api_version": row["api_version"], "waba_id": row["waba_id"],
                "app_id": row["app_id"], "hour_start": hours(row["hora_inicio"]),
                "hour_end": hours(row["hora_fin"]), "reminder_days": row["dias_recordatorio"],
                "max_retries": row["reintentos_max"],
                "daily_limit": row["limite_diario_por_cliente"],
                "silence_hours": row["horas_silencio_tras_agente"],
                "mora_interval_days": row["intervalo_mora_dias"],
                "mora_max_reminders": row["max_recordatorios_mora"]})
            settings_stage.created += 1
            settings_stage.notes.append(_(
                "Mensajería migrada apagada: se enciende el día del cambio. Token de acceso, "
                "secreto de la app y token de verificación de Meta: cargarlos a mano (estaban "
                "cifrados)."))
        for row in src.rows("messaging_ajustesbotia", [
                "soporte_activo", "ventas_activo", "modelo", "modelo_respaldo", "limite_diario",
                "instrucciones_ventas", "instrucciones_soporte", "quienes_somos"]):
            record = self.env["mirabilenet.bot.settings"]._load()
            if self._ref(record._name, "messaging_ajustesbotia", row["id"]):
                settings_stage.existing += 1
                continue
            self._bind("messaging_ajustesbotia", row["id"], record)
            record.write({
                "support_on": row["soporte_activo"], "sales_on": row["ventas_activo"],
                "model": row["modelo"], "backup_model": row["modelo_respaldo"] or False,
                "daily_limit": row["limite_diario"] or 0,
                "sales_style": row["instrucciones_ventas"],
                "support_style": row["instrucciones_soporte"],
                "about_us": row["quienes_somos"]})
            settings_stage.created += 1
        stages.append(settings_stage)
        alerts = src.scalar("SELECT COUNT(*) FROM {schema}.messaging_alertaintegracion")
        settings_stage.notes.append(_(
            "%s alertas de n8n del sistema anterior no se migran: son técnicas.", alerts))
        return stages

    # -- contenido web ---------------------------------------------------------
    def _stage_web(self, src):
        stages = []
        settings_stage = Stage("Configuración del sitio", 1)
        for row in src.rows("web_sitesettings", [
                "nombre_comercial", "lema", "descripcion", "titulo_portada", "imagen_portada",
                "frase_portada", "banda_titulo", "banda_texto", "telefono", "whatsapp",
                "email_ventas", "email_soporte", "direccion", "ciudad", "horario", "facebook",
                "instagram", "tiktok", "mostrar_planes_portada", "mostrar_planes",
                "aviso_legal"]):
            vals = {"trade_name": row["nombre_comercial"], "slogan": row["lema"],
                    "description": row["descripcion"] or False,
                    "hero_title": row["titulo_portada"] or False,
                    "hero_phrase": row["frase_portada"] or False,
                    "band_title": row["banda_titulo"] or False,
                    "band_text": row["banda_texto"] or False, "phone": row["telefono"] or False,
                    "whatsapp": row["whatsapp"] or False,
                    "sales_email": row["email_ventas"] or False,
                    "support_email": row["email_soporte"] or False,
                    "address": row["direccion"] or False, "city": row["ciudad"] or False,
                    "schedule": row["horario"] or False, "facebook": row["facebook"] or False,
                    "instagram": row["instagram"] or False, "tiktok": row["tiktok"] or False,
                    "show_plans_home": row["mostrar_planes_portada"],
                    "show_prices": row["mostrar_planes"],
                    "legal_notice": row["aviso_legal"] or False}
            image = self._file(row["imagen_portada"])
            if image:
                vals["hero_image"] = image
            elif row["imagen_portada"]:
                settings_stage.notes.append(_("Imagen de portada no disponible en la copia."))
            record = self.env["mirabilenet.web.settings"]._load()
            if self._ref(record._name, "web_sitesettings", row["id"]):
                settings_stage.existing += 1
                continue
            self._bind("web_sitesettings", row["id"], record)
            record.write(vals)
            settings_stage.created += 1
        stages.append(settings_stage)

        def simple(table, model, label, columns, build):
            rows = src.rows(table, columns)
            stage = Stage(label, len(rows))
            self._each(stage, table, model, rows, build)
            stages.append(stage)

        simple("web_ventaja", "mirabilenet.web.advantage", "Ventajas",
               ["icono", "titulo", "detalle", "orden", "activa"],
               lambda r: {"icon": r["icono"], "title": r["titulo"], "detail": r["detalle"] or False,
                          "sequence": r["orden"], "active": r["activa"]})
        simple("web_cifra", "mirabilenet.web.figure", "Cifras",
               ["icono", "valor", "etiqueta", "orden", "activa"],
               lambda r: {"icon": r["icono"], "value": r["valor"], "label": r["etiqueta"],
                          "sequence": r["orden"], "active": r["activa"]})
        simple("web_aliado", "mirabilenet.web.ally", "Tecnologías y aliados",
               ["nombre", "detalle", "orden", "activo"],
               lambda r: {"name": r["nombre"], "detail": r["detalle"] or False,
                          "sequence": r["orden"], "active": r["activo"]})
        simple("web_service", "mirabilenet.web.service", "Servicios del sitio",
               ["slug", "nombre", "resumen", "descripcion", "beneficios", "icono", "destacado",
                "orden", "activo"],
               lambda r: {"slug": r["slug"], "name": r["nombre"], "summary": r["resumen"],
                          "description": r["descripcion"] or False,
                          "benefits": r["beneficios"] or False, "icon": r["icono"],
                          "featured": r["destacado"], "sequence": r["orden"],
                          "active": r["activo"]})

        def coverage(r):
            region = self._r("mirabilenet.region", "core_region", r["region_id"])
            if not region:
                return "región %s sin migrar" % r["region_id"]
            return {"region_id": region.id, "name": r["nombre"], "detail": r["detalle"] or False,
                    "state": r["estado"], "sequence": r["orden"], "active": r["activa"]}
        simple("web_coveragelocality", "mirabilenet.web.coverage", "Cobertura",
               ["region_id", "nombre", "detalle", "estado", "orden", "activa"], coverage)

        def project(r):
            vals = {"slug": r["slug"], "title": r["titulo"], "kind": r["tipo"],
                    "summary": r["resumen"], "description": r["descripcion"] or False,
                    "location": r["ubicacion"] or False, "date": r["fecha"],
                    "sequence": r["orden"], "active": r["publicado"]}
            image = self._file(r["imagen"])
            if r["imagen"] and not image:
                return "imagen %s no disponible en la copia de media" % r["imagen"]
            if image:
                vals["image"] = image
            return vals
        simple("web_project", "mirabilenet.web.project", "Proyectos",
               ["slug", "titulo", "tipo", "resumen", "descripcion", "ubicacion", "fecha",
                "imagen", "orden", "publicado"], project)
        simple("web_faq", "mirabilenet.web.faq", "Preguntas frecuentes",
               ["pregunta", "respuesta", "categoria", "orden", "activa"],
               lambda r: {"question": r["pregunta"], "answer": r["respuesta"],
                          "category": r["categoria"], "sequence": r["orden"],
                          "active": r["activa"]})

        def legal(r):
            if self.env["mirabilenet.web.legal"].search_count([("kind", "=", r["clase"])]):
                return "ya hay un texto «%s» en Odoo: revisar cuál vale" % r["clase"]
            return {"kind": r["clase"], "title": r["titulo"], "summary": r["resumen"] or False,
                    "content": r["contenido"], "version": r["version"],
                    "valid_from": r["vigente_desde"]}
        simple("web_documentolegal", "mirabilenet.web.legal", "Textos legales",
               ["clase", "titulo", "resumen", "contenido", "version", "vigente_desde"], legal)

        def lead(r):
            return {"name": "%s: %s" % (r["tipo"], r["nombre"]), "type": "lead",
                    "contact_name": r["nombre"], "phone": r["telefono"] or False,
                    "email_from": r["email"] or False, "city": r["localidad"] or False,
                    "description": r["mensaje"] or False, "mirabilenet_kind": r["tipo"],
                    "mirabilenet_region_id": self._r("mirabilenet.region", "core_region",
                                                     r["region_id"]).id,
                    "mirabilenet_web_service_id": self._r("mirabilenet.web.service",
                                                          "web_service", r["servicio_id"]).id,
                    "mirabilenet_plan_interest": r["plan_interes"] or False,
                    "mirabilenet_status": r["estado"],
                    "mirabilenet_customer_id": self._r("res.partner", "crm_customer",
                                                       r["customer_id"]).id,
                    "mirabilenet_internal_note": r["nota_interna"] or False,
                    "mirabilenet_origin": "web:%s" % (r["pagina_origen"] or "/"),
                    "mirabilenet_source_ip": r["source_ip"] or False,
                    "mirabilenet_user_agent": r["user_agent"] or False}
        simple("web_lead", "crm.lead", "Consultas del sitio",
               ["tipo", "nombre", "telefono", "email", "localidad", "region_id", "servicio_id",
                "plan_interes", "mensaje", "estado", "customer_id", "nota_interna",
                "pagina_origen", "source_ip", "user_agent"], lead)
        return stages

    # -- AeroLab ---------------------------------------------------------------
    def _stage_aerolab(self, src):
        rows = src.rows("aerolab_dronecourse", [
            "region_id", "slug", "nombre", "nivel", "aplicacion", "resumen", "descripcion",
            "temario", "requisitos", "incluye", "fecha_inicio", "fecha_fin", "cupos_total",
            "precio", "precio_promocional", "estado", "publicado"])
        stage = Stage("Cursos de AeroLab → eventos", len(rows))
        provisional = 0

        def course(r):
            nonlocal provisional
            region = self._r("mirabilenet.region", "core_region", r["region_id"])
            if not region:
                return "región %s sin migrar" % r["region_id"]
            tags = self.env["event.tag"]
            for kind, key in (("level", r["nivel"]), ("application", r["aplicacion"])):
                tags |= self.env.ref("mirabilenet_aerolab.tag_%s_%s" % (kind, key),
                                     raise_if_not_found=False) or self.env["event.tag"]
            body = Markup("<p>%s</p>") % r["resumen"]
            if r["descripcion"]:
                body += Markup("<p>%s</p>") % r["descripcion"]
            for title, key in (("Temario", "temario"), ("Requisitos", "requisitos"),
                               ("Incluye", "incluye")):
                items = [l.strip() for l in (r[key] or "").splitlines() if l.strip()]
                if items:
                    body += Markup("<h3>%s</h3><ul>%s</ul>") % (title, Markup("").join(
                        Markup("<li>%s</li>") % escape(i) for i in items))
            confirmed = bool(r["fecha_inicio"])
            if not confirmed:
                provisional += 1
            start_day = r["fecha_inicio"] or fields.Date.context_today(self) + timedelta(days=30)
            end_day = r["fecha_fin"] or start_day
            price = r["precio_promocional"] if r["precio_promocional"] is not None else r["precio"]
            vals = {"name": r["nombre"], "mirabilenet_region_id": region.id,
                    "tag_ids": [(6, 0, tags.ids)], "description": body,
                    "date_begin": datetime.combine(start_day, time(13)),
                    "date_end": datetime.combine(end_day, time(17)),
                    "mirabilenet_date_confirmed": confirmed,
                    "seats_limited": bool(r["cupos_total"]), "seats_max": r["cupos_total"] or 0,
                    "event_ticket_ids": [(0, 0, {"name": "General", "price": price})]
                    if price and price > 0 else [], "website_published": False}
            return vals
        self._each(stage, "aerolab_dronecourse", "event.event", rows, course)
        # Se publica después de crear: así un curso incompleto queda en preparación, no rechazado.
        published = 0
        for r in rows:
            event = self._r("event.event", "aerolab_dronecourse", r["id"])
            if event and r["publicado"] and r["estado"] != "borrador" and not \
                    event._mirabilenet_missing_to_publish():
                event.website_published = True
                published += 1
        stage.notes.append(_("%(p)s cursos publicados; %(n)s sin fecha quedan con fecha "
                             "provisional y sin confirmar.", p=published, n=provisional))

        enrollments = src.rows("aerolab_courseenrollment", [
            "curso_id", "nombre", "ci", "telefono", "email", "estado", "monto_pagado"])
        enrollment_stage = Stage("Inscripciones a cursos", len(enrollments))
        question = self.env.ref("mirabilenet_aerolab.question_ci", raise_if_not_found=False)
        paid = 0

        def enrollment(r):
            nonlocal paid
            event = self._r("event.event", "aerolab_dronecourse", r["curso_id"])
            if not event:
                return "curso %s sin migrar" % r["curso_id"]
            if r["monto_pagado"]:
                paid += 1
            answers = [(0, 0, {"question_id": question.id, "value_text_box": r["ci"]})] \
                if question and r["ci"] else []
            return {"event_id": event.id, "name": r["nombre"], "email": r["email"] or False,
                    "phone": r["telefono"] or False, "state": ENROLLMENT_STATE[r["estado"]],
                    "registration_answer_ids": answers}
        self._each(enrollment_stage, "aerolab_courseenrollment", "event.registration",
                   enrollments, enrollment)
        enrollment_stage.notes.append(_(
            "Lista de espera y preinscripción pasan como «sin confirmar». %s inscripciones con "
            "monto pagado anotado a mano: el monto no tiene dónde ir en Odoo, revisarlas.", paid))
        return [stage, enrollment_stage]

    # -- pasantías -------------------------------------------------------------
    def _stage_internships(self, src):
        stages = []
        Employee = self.env["hr.employee"]
        rows = src.rows("pasantias_pasantia", ["usuario_id", "tutor_id", "institucion", "carrera",
                                               "horas_comprometidas", "estado"])
        stage = Stage("Pasantes (empleados practicantes)", len(rows))

        def intern(r):
            user = self._r("res.users", "core_user", r["usuario_id"])
            if not user:
                return "usuario %s sin migrar" % r["usuario_id"]
            tutor = self._r("res.users", "core_user", r["tutor_id"])
            coach = Employee.search([("user_id", "=", tutor.id)], limit=1) if tutor else Employee
            return {"name": user.name, "user_id": user.id, "employee_type": "trainee",
                    "coach_id": coach.id, "mirabilenet_institution": r["institucion"] or False,
                    "mirabilenet_career": r["carrera"] or False,
                    "mirabilenet_hours_committed": r["horas_comprometidas"],
                    "active": r["estado"] == "activa"}
        self._each(stage, "pasantias_pasantia", "hr.employee", rows, intern)
        stages.append(stage)

        projects = src.rows("pasantias_proyecto", ["nombre", "descripcion", "region_id"])
        project_stage = Stage("Proyectos de pasantías", len(projects))
        self._each(project_stage, "pasantias_proyecto", "project.project", projects,
                   lambda r: {"name": r["nombre"], "mirabilenet_internship": True,
                              "description": r["descripcion"] or False,
                              "mirabilenet_region_id": self._r(
                                  "mirabilenet.region", "core_region", r["region_id"]).id})
        stages.append(project_stage)

        tasks = {t["id"]: t for t in src.rows("pasantias_tarea", [
            "proyecto_id", "titulo", "descripcion", "instrucciones", "region_id", "fecha_limite",
            "pide_archivos", "pide_informe", "publicada"])}
        resources = {r["id"]: r for r in src.rows("pasantias_recurso", ["archivo",
                                                                        "nombre_original"])}
        task_resources = {}
        for link in src.rows("pasantias_tarea_recursos", ["tarea_id", "recurso_id"]):
            task_resources.setdefault(link["tarea_id"], []).append(link["recurso_id"])
        marks = {}
        for mark in src.rows("pasantias_itemmarcado", ["asignacion_id", "texto", "orden",
                                                       "obligatorio", "hecho"]):
            marks.setdefault(mark["asignacion_id"], []).append(mark)
        reports = {r["asignacion_id"]: r for r in src.rows(
            "pasantias_informeavance", ["asignacion_id", "horas_dedicadas"] + list(REPORT_FIELDS))}
        files = {}
        for item in src.rows("pasantias_archivo", ["asignacion_id", "archivo", "nombre_original"]):
            files.setdefault(item["asignacion_id"], []).append(item)
        comments = {}
        for item in src.rows("pasantias_comentario", ["asignacion_id", "autor_id", "texto"]):
            comments.setdefault(item["asignacion_id"], []).append(item)

        assignments = src.rows("pasantias_asignacion", [
            "tarea_id", "pasantia_id", "estado", "entregada_en", "comentario_pasante",
            "comentario_tutor"])
        task_stage = Stage("Tareas de pasantes (una por asignación)", len(assignments))
        missing_files = 0
        for a in assignments:
            if self._r("project.task", "pasantias_asignacion", a["id"]):
                task_stage.existing += 1
                continue
            t = tasks.get(a["tarea_id"])
            employee = self._r("hr.employee", "pasantias_pasantia", a["pasantia_id"])
            project = self._r("project.project", "pasantias_proyecto", t and t["proyecto_id"])
            if not t or not employee or not project:
                task_stage.reject("pasantias_asignacion", a["id"],
                                  "tarea, pasante o proyecto sin migrar (una tarea sin proyecto "
                                  "no tiene dónde ir)")
                continue
            try:
                with self.env.cr.savepoint():
                    description = Markup("<p>%s</p>") % (t["descripcion"] or "")
                    if t["instrucciones"]:
                        description += Markup("<p>%s</p>") % t["instrucciones"]
                    stage_ref = self.env.ref("mirabilenet_pasantias.%s" % INTERN_STAGE[a["estado"]])
                    task = self.env["project.task"].create({
                        "name": t["titulo"], "project_id": project.id,
                        "user_ids": [(6, 0, employee.user_id.ids)], "description": description,
                        "date_deadline": t["fecha_limite"],
                        "mirabilenet_published": t["publicada"],
                        "mirabilenet_requires_files": t["pide_archivos"],
                        "mirabilenet_requires_report": t["pide_informe"],
                        "stage_id": stage_ref.id,
                        "mirabilenet_delivered_at": a["entregada_en"],
                        "child_ids": [(0, 0, {
                            "name": m["texto"], "project_id": project.id,
                            "mirabilenet_required": m["obligatorio"],
                            "state": "1_done" if m["hecho"] else "01_in_progress",
                            "user_ids": [(6, 0, employee.user_id.ids)]})
                            for m in sorted(marks.get(a["id"], []), key=lambda m: m["orden"])]})
                    if a["estado"] in INTERN_STATE:
                        task.state = INTERN_STATE[a["estado"]]
                    report = reports.get(a["id"])
                    if report or a["comentario_tutor"]:
                        vals = {"task_id": task.id,
                                "tutor_comment": a["comentario_tutor"] or False}
                        if report:
                            vals.update({target: report[source] or False
                                         for source, target in REPORT_FIELDS.items()})
                            vals["hours"] = float(report["horas_dedicadas"] or 0)
                        task.mirabilenet_report_id = self.env[
                            "mirabilenet.internship.report"].create(vals)
                    attachments = list(files.get(a["id"], [])) + [
                        resources[rid] for rid in task_resources.get(t["id"], [])
                        if rid in resources]
                    for item in attachments:
                        content = self._file(item["archivo"])
                        if not content:
                            missing_files += 1
                            continue
                        self.env["ir.attachment"].create({
                            "name": item["nombre_original"], "datas": content,
                            "res_model": "project.task", "res_id": task.id})
                    if a["comentario_pasante"]:
                        task.message_post(body=a["comentario_pasante"],
                                          author_id=employee.user_id.partner_id.id,
                                          message_type="comment", subtype_xmlid="mail.mt_note")
                    for item in comments.get(a["id"], []):
                        author = self._r("res.users", "core_user", item["autor_id"])
                        task.message_post(body=item["texto"] or "-",
                                          author_id=author.partner_id.id or False,
                                          message_type="comment", subtype_xmlid="mail.mt_note")
                    self._bind("pasantias_asignacion", a["id"], task)
                    task_stage.created += 1
            except Exception as exc:  # pylint: disable=broad-except
                task_stage.reject("pasantias_asignacion", a["id"], str(exc).splitlines()[0][:200])
        if missing_files:
            task_stage.notes.append(_(
                "%s archivos de entregas o de material no estaban en la copia de media.",
                missing_files))
        stages.append(task_stage)
        return stages
