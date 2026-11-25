# Pruebas de autorización del SIN, etapas I a III (CUIS, catálogos, CUFD), contra PILOTO.
# Se ejecuta dentro de Odoo (odoo shell) con el módulo mira_sale_siat ya configurado:
#   docker compose run --rm --no-deps -T odoo odoo shell -c /etc/odoo/odoo.conf \
#       -d mirabilenet --no-http < etapas_1_a_3.py
# Variables opcionales: SIAT_REPETIR_CATALOGOS (50), SIAT_REPETIR_CUFD (100), SIAT_ETAPAS ("1,2,3").
# Solo corre en ambiente PILOTO. Guarda el avance tras cada llamada correcta.
import os
import time
import uuid

from odoo.addons.mira_sale_siat.siat import constants

REP_CAT = int(os.environ.get("SIAT_REPETIR_CATALOGOS", "50"))
REP_CUFD = int(os.environ.get("SIAT_REPETIR_CUFD", "100"))
ETAPAS = set(os.environ.get("SIAT_ETAPAS", "1,2,3").split(","))
EXTRA_SYNC = ["sincronizarFechaHora", "sincronizarParametricaTipoHabitacion"]


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


company = env["res.company"].search([("mira_siat_enabled", "=", True)], limit=1)
assert company, "No hay empresa con SIAT activo."
assert company.mira_siat_environment == "2", "Solo se corre en PILOTO."
assert company.mira_siat_gateway_mode == "real", "El SIAT está en simulador."
Pos = env["mira.siat.pos"].sudo()
main = Pos.search([("company_id", "=", company.id), ("code", "=", 0)], order="branch_id", limit=1)
log("Empresa %s, sucursal %s" % (company.name, main.branch_id.code))

# ---------------- Etapa I: caja 1 registrada y con CUIS ----------------
caja = Pos.search([("branch_id", "=", main.branch_id.id), ("code", "!=", 0)], limit=1)
if "1" in ETAPAS:
    if not caja:
        tipos = env["mira.siat.catalog.item"].sudo().search(
            [("company_id", "=", company.id), ("catalog_type", "=", "tipo_punto_venta")])
        for t in tipos:
            log("  tipo de punto de venta %s: %s" % (t.code, t.name))
        tipo = tipos.filtered(lambda t: "CAJERO" in (t.name or "").upper())[:1] or tipos[:1]
        caja = Pos.create({"branch_id": main.branch_id.id, "register_new": True,
                           "name": "%s - Caja 1" % main.branch_id.name, "pos_type_id": tipo.id})
        caja._register_with_sin()
        env.cr.commit()
        log("Caja registrada ante el SIN con el código %s (tipo %s)" % (caja.code, tipo.name))
    for pos in main | caja:
        pos._renew_cuis()
        env.cr.commit()
        log("Etapa I: CUIS pedido para el punto de venta %s" % pos.code)

puntos = (main | caja).filtered(lambda p: p.code >= 0)

# ---------------- Etapa II: sincronización de catálogos ----------------
if "2" in ETAPAS:
    for pos in puntos:
        ctx = pos._siat_context()
        cuis = pos._get_cuis()._code()
        base = {"codigoAmbiente": ctx.environment, "codigoPuntoVenta": ctx.pos_code,
                "codigoSistema": ctx.system_code, "codigoSucursal": ctx.branch_code,
                "cuis": cuis, "nit": ctx.nit}
        metodos = [op for op, _tag in constants.CATALOG_OPERATIONS.values()] + EXTRA_SYNC
        for metodo in metodos:
            bien = mal = 0
            for _i in range(REP_CAT):
                try:
                    gw = company._mira_siat_gateway(str(uuid.uuid4()))
                    data = gw.client.call(constants.SERVICE_SYNC, metodo,
                                          "SolicitudSincronizacion", dict(sorted(base.items())))
                    if str(data.get("transaccion")).lower() == "true":
                        bien += 1
                    else:
                        mal += 1
                        if mal <= 2:
                            log("  %s rechazado: %s" % (metodo, data.get("mensajesList")))
                except Exception as exc:  # se sigue con la siguiente llamada
                    mal += 1
                    if mal <= 2:
                        log("  %s error: %s" % (metodo, exc))
            log("Etapa II PV %s %s: %s correctas, %s fallidas" % (pos.code, metodo, bien, mal))

# ---------------- Etapa III: CUFD ----------------
if "3" in ETAPAS:
    for pos in puntos:
        bien = mal = 0
        for _i in range(REP_CUFD):
            try:
                pos._renew_cufd()
                env.cr.commit()
                bien += 1
            except Exception as exc:
                env.cr.rollback()
                mal += 1
                if mal <= 3:
                    log("  CUFD PV %s error: %s" % (pos.code, exc))
        log("Etapa III PV %s: %s CUFD correctos, %s fallidos" % (pos.code, bien, mal))

env.cr.commit()
log("FIN etapas %s" % ",".join(sorted(ETAPAS)))
