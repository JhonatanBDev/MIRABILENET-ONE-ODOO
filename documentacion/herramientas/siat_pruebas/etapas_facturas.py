# Pruebas de autorización del SIN con facturas, contra PILOTO, usando el flujo real de
# mira_sale_siat (las mismas funciones que usa la pantalla).
#   docker compose run --rm --no-deps -T -e SIAT_ETAPA=4 -e SIAT_CANTIDAD=125 odoo \
#       odoo shell -c /etc/odoo/odoo.conf -d mirabilenet --no-http < etapas_facturas.py
# SIAT_ETAPA:
#   4  emisión individual en línea: SIAT_CANTIDAD facturas por punto de venta.
#   7  anulación: anula SIAT_CANTIDAD facturas válidas por punto de venta (motivo 1).
#   11 reversión: revierte SIAT_CANTIDAD facturas anuladas por punto de venta.
#   5  eventos significativos con paquetes: por cada tipo de evento en SIAT_EVENTOS
#      ("1,2,3,4,5,6,7") y punto de venta, SIAT_CANTIDAD eventos, cada uno con
#      SIAT_FACTURAS_EVENTO facturas fuera de línea enviadas y validadas en paquete.
# Solo corre en PILOTO. Guarda el avance tras cada operación.
import os
import time

from odoo import fields

ETAPA = os.environ.get("SIAT_ETAPA", "4")
CANTIDAD = int(os.environ.get("SIAT_CANTIDAD", "1"))
EVENTOS = [e for e in os.environ.get("SIAT_EVENTOS", "1,2,3,4,5,6,7").split(",") if e]
FACT_EVENTO = int(os.environ.get("SIAT_FACTURAS_EVENTO", "1"))
SOLO_PV = os.environ.get("SIAT_PV")  # p. ej. "0" para un solo punto de venta


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


company = env["res.company"].search([("mira_siat_enabled", "=", True)], limit=1)
assert company.mira_siat_environment == "2", "Solo se corre en PILOTO."
assert company.mira_siat_gateway_mode == "real", "El SIAT está en simulador."
env = env(context=dict(env.context, allowed_company_ids=[company.id]))
Item = env["mira.siat.catalog.item"].sudo()


def item(tipo, code=None, activity=None):
    dom = [("company_id", "=", company.id), ("catalog_type", "=", tipo)]
    if code is not None:
        dom.append(("code", "=", str(code)))
    if activity:
        dom.append(("activity_code", "=", activity))
    found = Item.search(dom, limit=1)
    assert found, "Falta en el catálogo %s el código %s" % (tipo, code)
    return found


# ---------------- cliente y producto de prueba ----------------
ACTIVIDAD = "6190200"
partner = env["res.partner"].search([("name", "=", "CLIENTE PRUEBAS SIAT")], limit=1)
if not partner:
    partner = env["res.partner"].create({"name": "CLIENTE PRUEBAS SIAT", "vat": "1234567"})
partner.with_company(company).mira_siat_doc_type_id = item("tipo_documento_identidad", 1)
product = env["product.product"].search([("default_code", "=", "PRUEBA-SIAT")], limit=1)
if not product:
    product = env["product.product"].create({
        "name": "SERVICIO DE INTERNET (PRUEBA SIAT)", "default_code": "PRUEBA-SIAT",
        "type": "service", "list_price": 100.0, "taxes_id": [(6, 0, [])]})
product.product_tmpl_id.with_company(company).write({
    "mira_siat_activity_id": item("actividades", ACTIVIDAD).id,
    "mira_siat_product_id": Item.search([
        ("company_id", "=", company.id), ("catalog_type", "=", "productos_servicios"),
        ("activity_code", "=", ACTIVIDAD)], limit=1).id or item("productos_servicios").id,
    "mira_siat_unit_id": item("unidad_medida", 58).id,
})
PAGO = item("tipo_metodo_pago", 6)  # PAGO POSTERIOR: la factura de prueba no tiene cobro
env.cr.commit()

puntos = env["mira.siat.pos"].sudo().search(
    [("company_id", "=", company.id), ("code", ">=", 0)], order="code")
if SOLO_PV is not None:
    puntos = puntos.filtered(lambda p: p.code == int(SOLO_PV))
Invoice = env["mira.siat.invoice"].sudo()


def nueva_factura(pos, precio=100.0):
    move = env["account.move"].with_company(company).create({
        "move_type": "out_invoice", "partner_id": partner.id,
        "invoice_date": fields.Date.context_today(partner),
        "mira_siat_pos_id": pos.id,
        "mira_siat_payment_method_id": PAGO.id, "mira_siat_payment_method_manual": True,
        "invoice_line_ids": [(0, 0, {"product_id": product.id, "quantity": 1,
                                     "price_unit": precio, "tax_ids": [(6, 0, [])]})],
    })
    move.action_post()
    move.action_mira_siat_issue()
    doc = Invoice.search([("move_id", "=", move.id)], order="id desc", limit=1)
    env.cr.commit()
    # Si el SIN tardó en contestar, se consulta y reintenta (no se emite otra factura).
    for _intento in range(3):
        if doc.state != "pending_retry":
            break
        time.sleep(2)
        doc._retry()
        env.cr.commit()
    return doc


def resumen(pos, etiqueta, bien, mal):
    log("%s PV %s: %s correctas, %s fallidas" % (etiqueta, pos.code, bien, mal))


# ---------------- Etapa IV: emisión individual ----------------
if ETAPA == "4":
    for pos in puntos:
        bien = mal = 0
        for i in range(CANTIDAD):
            try:
                doc = nueva_factura(pos, 100.0 + i)
                env.cr.commit()
                if doc.state == "valid":
                    bien += 1
                else:
                    mal += 1
                    if mal <= 3:
                        log("  factura %s: estado %s %s %s" % (
                            doc.id, doc.state, doc.error_code or "", doc.siat_messages or ""))
            except Exception as exc:
                env.cr.rollback()
                mal += 1
                if mal <= 3:
                    log("  error al emitir: %s" % exc)
        resumen(pos, "Etapa IV", bien, mal)

# ---------------- Etapa VII: anulación ----------------
if ETAPA == "7":
    motivo = item("motivo_anulacion", 1)
    for pos in puntos:
        docs = Invoice.search([("pos_id", "=", pos.id), ("state", "=", "valid"),
                               ("move_id.partner_id", "=", partner.id)], limit=CANTIDAD)
        bien = mal = 0
        for doc in docs:
            try:
                doc._cancel(motivo)
                env.cr.commit()
                bien += doc.state == "cancelled"
                mal += doc.state != "cancelled"
            except Exception as exc:
                env.cr.rollback()
                mal += 1
                if mal <= 3:
                    log("  error al anular %s: %s" % (doc.id, exc))
        resumen(pos, "Etapa VII (de %s disponibles)" % len(docs), bien, mal)

# ---------------- Etapa XI: reversión ----------------
if ETAPA == "11":
    for pos in puntos:
        docs = Invoice.search([("pos_id", "=", pos.id), ("state", "=", "cancelled"),
                               ("move_id.partner_id", "=", partner.id)], limit=CANTIDAD)
        bien = mal = 0
        for doc in docs:
            try:
                doc.action_revert_cancellation()
                env.cr.commit()
                bien += doc.state == "valid"
                mal += doc.state != "valid"
            except Exception as exc:
                env.cr.rollback()
                mal += 1
                if mal <= 3:
                    log("  error al revertir %s: %s" % (doc.id, exc))
        resumen(pos, "Etapa XI (de %s disponibles)" % len(docs), bien, mal)

# ---------------- Etapas V y VI: eventos y paquetes ----------------
if ETAPA == "5":
    Event = env["mira.siat.event"].sudo()
    for pos in puntos:
        for codigo in EVENTOS:
            tipo = item("eventos_significativos", codigo)
            bien = mal = 0
            for _n in range(CANTIDAD):
                try:
                    event = Event.create({"pos_id": pos.id, "event_type_id": tipo.id,
                                          "description": tipo.name[:100]})
                    event.action_start()
                    env.cr.commit()
                    for _f in range(FACT_EVENTO):
                        nueva_factura(pos)
                        env.cr.commit()
                    event.action_close()
                    event.action_register()
                    env.cr.commit()
                    event.action_send_packages()
                    env.cr.commit()
                    time.sleep(3)  # el SIN valida el paquete de forma asíncrona
                    event.action_validate_packages()
                    env.cr.commit()
                    ok = event.state == "done" and event.reception_code
                    bien += bool(ok)
                    mal += not ok
                    if not ok and mal <= 3:
                        log("  evento %s quedó en %s" % (event.id, event.state))
                except Exception as exc:
                    env.cr.rollback()
                    mal += 1
                    if mal <= 3:
                        log("  evento %s error: %s" % (codigo, exc))
            resumen(pos, "Etapas V/VI evento %s" % codigo, bien, mal)

env.cr.commit()
log("FIN etapa %s" % ETAPA)
