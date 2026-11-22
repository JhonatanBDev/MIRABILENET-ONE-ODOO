"""La migración contra tablas de prueba con el esquema del sistema anterior, en un esquema
aparte de la propia base (se deshace al terminar cada prueba)."""
import base64
import json
import os
import shutil
import tempfile
from datetime import date, datetime, time
from decimal import Decimal

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from ..migracion.source import SourceError, SourceReader
from ..models.mirabilenet_migration import MigrationMismatch

SCHEMA = "origen_prueba"
TABLES = {
    "core_region": "code varchar, name varchar, wg_region_id int, active bool, dia_emision int, "
                   "dia_vencimiento int, dia_emision_prepago int, "
                   "prorrateo_prepago_activacion bool, prorrateo_prepago_desde date, "
                   "dias_gracia int, hora_corte time, suspension_automatica bool, "
                   "reactivacion_automatica bool, moneda varchar, objetivo_mrr numeric, "
                   "precio_referencia numeric",
    "core_branch": "region_id int, code varchar, name varchar, address varchar, "
                   "phone varchar, active bool",
    "core_zone": "region_id int, code varchar, name varchar, sector varchar, active bool",
    "core_node": "zone_id int, code varchar, name varchar, latitude numeric, "
                 "longitude numeric, capacidad_instalada int, active bool",
    "core_user": "username varchar, first_name varchar, last_name varchar, email varchar, "
                 "is_active bool, role varchar, region_id int, branch_id int",
    "crm_customer": "code varchar, tipo varchar, nombre varchar, documento varchar, "
                    "telefono varchar, whatsapp varchar, email varchar, direccion varchar, "
                    "region_id int, zone_id int, branch_id int, estado varchar, "
                    "vendedor_id int, contacto_verificado bool, notas text, "
                    "requiere_factura bool, nit_facturacion varchar, "
                    "razon_social_facturacion varchar, complemento_documento varchar",
    "crm_customercontact": "customer_id int, nombre varchar, cargo varchar, telefono varchar, "
                           "email varchar, autorizado_soporte bool, autorizado_pagos bool",
    "isp_plan": "region_id int, code varchar, nombre varchar, bajada_mbps int, "
                "subida_mbps int, precio numeric, perfil_ppp varchar, perfil_reducido varchar, "
                "incluye_tv bool, activo bool, publicar_en_web bool",
    "isp_router": "region_id int, zone_id int, node_id int, nombre varchar, modelo varchar, "
                  "tipo_equipo varchar, routeros_version varchar, funcion varchar, "
                  "modo_control varchar, wg_ip varchar, wg_public_key varchar, "
                  "identity varchar, serial varchar, board_name varchar, api_user varchar, "
                  "api_port int, api_address_before varchar, lan_networks text, "
                  "estado varchar, api_password text",
    "isp_networksubnet": "region_id int, site_id int, cidr varchar, tipo varchar, "
                         "estado varchar, customer_id int, descripcion varchar, "
                         "red_heredada varchar",
    "isp_service": "customer_id int, region_id int, node_id int, router_id int, plan_id int, "
                   "estado varchar, modalidad_pago varchar, fecha_alta date, fecha_baja date, "
                   "dia_facturacion int, precio_mensual numeric, "
                   "direccion_instalacion varchar, observaciones text",
    "isp_pppoeaccount": "service_id int, username varchar, ip_fija varchar, perfil varchar, "
                        "caller_id varchar, habilitado bool, password text",
    "billing_charge": "numero varchar, customer_id int, service_id int, region_id int, "
                      "concepto varchar, fecha_emision date, fecha_vencimiento date, "
                      "monto_total numeric, saldo numeric, estado varchar",
    "billing_payment": "customer_id int, region_id int, monto numeric, metodo varchar, "
                       "referencia varchar, fecha_pago timestamptz, estado varchar",
    "billing_paymentallocation": "payment_id int, charge_id int, monto numeric",
    "billing_receipt": "payment_id int, numero varchar, anulado bool, anula_a_id int",
}

TABLES.update({
    "inventory_warehouse": "branch_id int, code varchar, nombre varchar, responsable_id int, "
                           "activo bool",
    "inventory_inventoryitem": "sku varchar, categoria varchar, marca varchar, modelo varchar, "
                               "descripcion varchar, serializado bool, unidad varchar, "
                               "costo numeric, precio_venta numeric, stock_minimo int, activo bool",
    "inventory_inventoryserial": "item_id int, serial varchar, mac varchar, region_id int, "
                                 "warehouse_id int, tecnico_id int, customer_id int, "
                                 "estado varchar, proveedor varchar, fecha_compra date, "
                                 "garantia_hasta date, costo numeric",
    "inventory_inventorystock": "item_id int, warehouse_id int, cantidad numeric",
    "inventory_inventorymovement": "tipo varchar",
    "messaging_branchwhatsappnumber": "branch_id int, phone_number_id varchar, "
                                      "numero_visible varchar, nombre_remitente varchar, "
                                      "activo bool, compartido_global bool, modo varchar, "
                                      "verificado_at timestamptz, plataforma_meta varchar, "
                                      "ultimo_error varchar",
    "messaging_messagetemplate": "evento varchar, region_id int, nombre_meta varchar, "
                                 "idioma varchar, parameter_format varchar, variables jsonb, "
                                 "texto_referencia text, incluir_qr_encabezado bool, activo bool",
    "messaging_whatsappoptout": "customer_id int, motivo varchar, origen varchar",
    "messaging_whatsappconsentimiento": "customer_id int, origen varchar, detalle varchar, "
                                        "otorgado_at timestamptz, registrado_por_id int",
    "messaging_regionalpaymentqr": "region_id int, image varchar, active bool, "
                                   "uploaded_by_id int",
    "messaging_conversacion": "canal varchar, contacto varchar, customer_id int, region_id int, "
                              "numero_origen_id int, estado varchar, atendida_por_id int, "
                              "ultimo_entrante_at timestamptz, ultimo_saliente_at timestamptz, "
                              "revisada_at timestamptz",
    "messaging_mensajeconversacion": "conversacion_id int, direccion varchar, origen varchar, "
                                     "tipo varchar, texto text, datos jsonb, id_externo varchar, "
                                     "clave_unica varchar, estado varchar, "
                                     "error_detalle varchar, enviado_at timestamptz",
    "messaging_whatsappmessage": "customer_id int, charge_id int, region_id int, "
                                 "numero_origen_id int, template_id int, evento varchar, "
                                 "destino varchar, parametros jsonb, header_image_url varchar, "
                                 "estado varchar, intentos int, wa_message_id varchar, "
                                 "error_codigo varchar, error_detalle varchar, "
                                 "clave_unica varchar, enviado_at timestamptz, "
                                 "entregado_at timestamptz, leido_at timestamptz",
    "messaging_whatsappproof": "customer_id int, charge_id int, file varchar, mime_type varchar, "
                               "size_bytes int, whatsapp_message_id varchar, estado varchar, "
                               "payment_id int, motivo_rechazo varchar, simulado bool, "
                               "revisado_at timestamptz, revisado_por_id int",
    "messaging_whatsappsupportcase": "customer_id int, tipo varchar, motivo text, "
                                     "estado varchar, assigned_to_id int, "
                                     "inbound_message_id varchar, conversacion_id int, "
                                     "resolved_at timestamptz",
    "messaging_promocionretencion": "nombre varchar, descripcion varchar, condiciones varchar, "
                                    "region_id int, vigente_desde date, vigente_hasta date, "
                                    "activa bool, orden int",
    "messaging_whatsappsettings": "activo bool, modo_prueba bool, exigir_consentimiento bool, "
                                  "api_version varchar, waba_id varchar, app_id varchar, "
                                  "hora_inicio time, hora_fin time, dias_recordatorio int, "
                                  "reintentos_max int, limite_diario_por_cliente int, "
                                  "horas_silencio_tras_agente int, intervalo_mora_dias int, "
                                  "max_recordatorios_mora int",
    "messaging_ajustesbotia": "soporte_activo bool, ventas_activo bool, modelo varchar, "
                              "modelo_respaldo varchar, limite_diario int, "
                              "instrucciones_ventas text, instrucciones_soporte text, "
                              "quienes_somos text",
    "messaging_alertaintegracion": "workflow varchar",
    "web_sitesettings": "nombre_comercial varchar, lema varchar, descripcion text, "
                        "titulo_portada varchar, imagen_portada varchar, frase_portada varchar, "
                        "banda_titulo varchar, banda_texto varchar, telefono varchar, "
                        "whatsapp varchar, email_ventas varchar, email_soporte varchar, "
                        "direccion varchar, ciudad varchar, horario varchar, facebook varchar, "
                        "instagram varchar, tiktok varchar, mostrar_planes_portada bool, "
                        "mostrar_planes bool, aviso_legal text",
    "web_ventaja": "icono varchar, titulo varchar, detalle varchar, orden int, activa bool",
    "web_cifra": "icono varchar, valor varchar, etiqueta varchar, orden int, activa bool",
    "web_aliado": "nombre varchar, detalle varchar, orden int, activo bool",
    "web_service": "slug varchar, nombre varchar, resumen varchar, descripcion text, "
                   "beneficios text, icono varchar, destacado bool, orden int, activo bool",
    "web_coveragelocality": "region_id int, nombre varchar, detalle varchar, estado varchar, "
                            "orden int, activa bool",
    "web_project": "slug varchar, titulo varchar, tipo varchar, resumen varchar, "
                   "descripcion text, ubicacion varchar, fecha date, imagen varchar, orden int, "
                   "publicado bool",
    "web_faq": "pregunta varchar, respuesta text, categoria varchar, orden int, activa bool",
    "web_documentolegal": "clase varchar, titulo varchar, resumen varchar, contenido text, "
                          "version varchar, vigente_desde date",
    "web_lead": "tipo varchar, nombre varchar, telefono varchar, email varchar, "
                "localidad varchar, region_id int, servicio_id int, plan_interes varchar, "
                "mensaje text, estado varchar, customer_id int, nota_interna text, "
                "pagina_origen varchar, source_ip varchar, user_agent varchar",
    "aerolab_dronecourse": "region_id int, slug varchar, nombre varchar, nivel varchar, "
                           "aplicacion varchar, resumen varchar, descripcion text, "
                           "temario text, requisitos text, incluye text, fecha_inicio date, "
                           "fecha_fin date, cupos_total int, precio numeric, "
                           "precio_promocional numeric, estado varchar, publicado bool",
    "aerolab_courseenrollment": "curso_id int, nombre varchar, ci varchar, telefono varchar, "
                                "email varchar, estado varchar, monto_pagado numeric",
    "pasantias_pasantia": "usuario_id int, tutor_id int, institucion varchar, carrera varchar, "
                          "horas_comprometidas int, estado varchar",
    "pasantias_proyecto": "nombre varchar, descripcion text, region_id int",
    "pasantias_recurso": "archivo varchar, nombre_original varchar",
    "pasantias_tarea": "proyecto_id int, titulo varchar, descripcion text, instrucciones text, "
                       "region_id int, fecha_limite timestamptz, pide_archivos bool, "
                       "pide_informe bool, publicada bool",
    "pasantias_tarea_recursos": "tarea_id int, recurso_id int",
    "pasantias_itemmarcado": "asignacion_id int, texto varchar, orden int, obligatorio bool, "
                             "hecho bool",
    "pasantias_informeavance": "asignacion_id int, horas_dedicadas numeric, objetivo text, "
                               "resumen text, actividades text, herramientas text, "
                               "parametros text, resultados text, validacion text, "
                               "justificacion text, dificultades text, proximos_pasos text, "
                               "referencias text",
    "pasantias_archivo": "asignacion_id int, archivo varchar, nombre_original varchar",
    "pasantias_comentario": "asignacion_id int, autor_id int, texto text",
    "pasantias_asignacion": "tarea_id int, pasantia_id int, estado varchar, "
                            "entregada_en timestamptz, comentario_pasante text, "
                            "comentario_tutor text",
})

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4//8/AwAI/AL+p5qgoAAAAABJRU5ErkJggg==")


@tagged("mirabilenet", "post_install", "-at_install")
class TestMigracion(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref("base.user_root"))
        if not cls.env["account.journal"].search_count(
                [("type", "=", "cash"), ("company_id", "=", cls.env.company.id)]):
            cls.env["account.journal"].create(
                {"name": "Caja", "code": "CAJA", "type": "cash"})

    def setUp(self):
        super().setUp()
        cr = self.env.cr
        cr.execute("CREATE SCHEMA %s" % SCHEMA)
        for table, columns in TABLES.items():
            cr.execute("CREATE TABLE %s.%s (id int PRIMARY KEY, %s)" % (SCHEMA, table, columns))
        self._fill()
        self._fill_rest()
        self.src = SourceReader(cr, SCHEMA)
        self.media = tempfile.mkdtemp()
        self.private = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        self.addCleanup(shutil.rmtree, self.private, True)
        for root, rel, content in ((self.media, "payment-qrs/1/qr.png", PNG),
                                   (self.media, "pasantias/1/plano.dxf", b"0 SECTION"),
                                   (self.private, "whatsapp-proofs/1/c.pdf", b"%PDF-1.4 x")):
            os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
            with open(os.path.join(root, rel), "wb") as handle:
                handle.write(content)
        self.Migration = self.env["mirabilenet.migration"].with_context(
            mirabilenet_media_root=self.media, mirabilenet_private_root=self.private)

    def _insert(self, table, rows):
        for row in rows:
            columns = ", ".join(row)
            marks = ", ".join(["%s"] * len(row))
            self.env.cr.execute("INSERT INTO %s.%s (%s) VALUES (%s)" % (
                SCHEMA, table, columns, marks), list(row.values()))

    def _fill(self):
        self._insert("core_region", [dict(
            id=1, code="M-T", name="Migrada", wg_region_id=43, active=True, dia_emision=1,
            dia_vencimiento=10, dia_emision_prepago=1, prorrateo_prepago_activacion=False,
            prorrateo_prepago_desde=None, dias_gracia=3, hora_corte=time(9, 30),
            suspension_automatica=True, reactivacion_automatica=True, moneda="BOB",
            objetivo_mrr=5000, precio_referencia=200)])
        self._insert("core_branch", [dict(id=1, region_id=1, code="MT1", name="Centro",
                                          address="", phone="", active=True)])
        self._insert("core_zone", [dict(id=1, region_id=1, code="MZ1", name="Zona",
                                        sector="", active=True)])
        self._insert("core_node", [dict(id=1, zone_id=1, code="MN1", name="Nodo",
                                        latitude=None, longitude=None, capacidad_instalada=20,
                                        active=True)])
        self._insert("core_user", [
            dict(id=1, username="m_admin", first_name="Ana", last_name="Rojas", email="",
                 is_active=True, role="admin_regional", region_id=1, branch_id=1),
            dict(id=2, username="m_portal", first_name="", last_name="", email="",
                 is_active=True, role="cliente_residencial", region_id=None, branch_id=None)])
        customer = dict(tipo="residencial", documento="1234567", telefono="70000001",
                        whatsapp="59170000001", email="", direccion="Calle 1", zone_id=1,
                        branch_id=1, estado="activo", vendedor_id=1, contacto_verificado=True,
                        notas="", requiere_factura=False, nit_facturacion="",
                        razon_social_facturacion="", complemento_documento="")
        self._insert("crm_customer", [
            dict(customer, id=1, code="MT-0001", nombre="Cliente Uno", region_id=1),
            dict(customer, id=2, code="MT-0002", nombre="Sin región", region_id=99)])
        self._insert("crm_customercontact", [dict(
            id=1, customer_id=1, nombre="Hijo", cargo="", telefono="70000002", email="",
            autorizado_soporte=True, autorizado_pagos=False)])
        self._insert("isp_plan", [dict(
            id=1, region_id=1, code="M-HOGAR", nombre="Hogar 20", bajada_mbps=20, subida_mbps=10,
            precio=300, perfil_ppp="", perfil_reducido="", incluye_tv=False, activo=True,
            publicar_en_web=True)])
        self._insert("isp_router", [dict(
            id=1, region_id=1, zone_id=1, node_id=1, nombre="RB-MIGRADO", modelo="hAP",
            tipo_equipo="routerboard", routeros_version="7.15", funcion="pppoe",
            modo_control="api", wg_ip="10.250.239.10", wg_public_key="", identity="",
            serial="", board_name="", api_user="mirabilenet", api_port=8728,
            api_address_before="", lan_networks="", estado="conectado",
            api_password="gAAAAAcifrado")])
        self._insert("isp_service", [dict(
            id=1, customer_id=1, region_id=1, node_id=1, router_id=1, plan_id=1,
            estado="activo", modalidad_pago="pospago", fecha_alta=date(2026, 1, 5),
            fecha_baja=None, dia_facturacion=1, precio_mensual=300,
            direccion_instalacion="Calle 1", observaciones="")])
        self._insert("isp_pppoeaccount", [dict(
            id=1, service_id=1, username="cliente.uno", ip_fija=None, perfil="",
            caller_id="", habilitado=True, password="gAAAAAcifrado")])
        charge = dict(customer_id=1, service_id=1, region_id=1, concepto="Hogar 20",
                      monto_total=300)
        self._insert("billing_charge", [
            dict(charge, id=1, numero="AV-1", fecha_emision=date(2026, 8, 1),
                 fecha_vencimiento=date(2026, 8, 10), saldo=0, estado="pagado"),
            dict(charge, id=2, numero="AV-2", fecha_emision=date(2026, 9, 1),
                 fecha_vencimiento=date(2026, 9, 10), saldo=100, estado="pago_parcial"),
            dict(charge, id=3, numero="AV-3", fecha_emision=date(2026, 10, 1),
                 fecha_vencimiento=date(2026, 10, 10), saldo=300, estado="vencido"),
            dict(charge, id=4, numero="AV-4", fecha_emision=date(2026, 10, 1),
                 fecha_vencimiento=date(2026, 10, 10), saldo=0, estado="anulado")])
        moment = datetime(2026, 9, 15, 14, 0)
        self._insert("billing_payment", [
            dict(id=1, customer_id=1, region_id=1, monto=300, metodo="efectivo",
                 referencia="", fecha_pago=moment, estado="aprobado"),
            dict(id=2, customer_id=1, region_id=1, monto=250, metodo="qr",
                 referencia="QR-9", fecha_pago=moment, estado="aprobado"),
            dict(id=3, customer_id=1, region_id=1, monto=999, metodo="qr",
                 referencia="", fecha_pago=moment, estado="rechazado")])
        self._insert("billing_paymentallocation", [
            dict(id=1, payment_id=1, charge_id=1, monto=300),
            dict(id=2, payment_id=2, charge_id=2, monto=200)])
        self._insert("billing_receipt", [
            dict(id=1, payment_id=1, numero="MN-MT1-C1-000045", anulado=False, anula_a_id=None)])

    def _fill_rest(self):
        moment = datetime(2026, 9, 15, 14, 0)
        self._insert("core_user", [dict(id=3, username="m_pasante", first_name="Luis",
                                        last_name="Paz", email="", is_active=True,
                                        role="pasante", region_id=1, branch_id=None)])
        self._insert("inventory_warehouse", [
            dict(id=1, branch_id=1, code="ALM1", nombre="Almacén centro", responsable_id=1,
                 activo=True),
            dict(id=2, branch_id=1, code="ALMACEN-LARGO", nombre="Otro", responsable_id=None,
                 activo=True)])
        self._insert("inventory_inventoryitem", [
            dict(id=1, sku="RT-1", categoria="router", marca="MikroTik", modelo="hAP",
                 descripcion="Router hAP", serializado=True, unidad="unidad", costo=300,
                 precio_venta=450, stock_minimo=2, activo=True),
            dict(id=2, sku="CAB-1", categoria="fibra", marca="", modelo="", descripcion="Fibra",
                 serializado=False, unidad="m", costo=1, precio_venta=2, stock_minimo=100,
                 activo=True)])
        serial = dict(item_id=1, mac="", region_id=1, tecnico_id=None, customer_id=None,
                      proveedor="", fecha_compra=None, garantia_hasta=None, costo=300)
        self._insert("inventory_inventoryserial", [
            dict(serial, id=1, serial="SN-1", warehouse_id=1, estado="en_almacen"),
            dict(serial, id=2, serial="SN-2", warehouse_id=None, estado="en_cliente",
                 customer_id=1)])
        self._insert("inventory_inventorystock", [
            dict(id=1, item_id=1, warehouse_id=1, cantidad=1),
            dict(id=2, item_id=2, warehouse_id=1, cantidad=250)])
        self._insert("inventory_inventorymovement", [dict(id=1, tipo="compra")])
        self._insert("messaging_branchwhatsappnumber", [dict(
            id=1, branch_id=1, phone_number_id="PN-1", numero_visible="+59170000000",
            nombre_remitente="MIRABILENET", activo=True, compartido_global=False,
            modo="api_pura", verificado_at=None, plataforma_meta="", ultimo_error="")])
        self._insert("messaging_messagetemplate", [dict(
            id=1, evento="aviso_emitido", region_id=None, nombre_meta="aviso_cobro", idioma="es",
            parameter_format="POSITIONAL", variables=json.dumps(["cliente", "saldo"]),
            texto_referencia="", incluir_qr_encabezado=False, activo=True)])
        self._insert("messaging_whatsappoptout", [dict(id=1, customer_id=1, motivo="",
                                                       origen="cliente")])
        self._insert("messaging_whatsappconsentimiento", [dict(
            id=1, customer_id=1, origen="contrato", detalle="Contrato", otorgado_at=moment,
            registrado_por_id=1)])
        self._insert("messaging_regionalpaymentqr", [dict(
            id=1, region_id=1, image="payment-qrs/1/qr.png", active=True, uploaded_by_id=1)])
        self._insert("messaging_conversacion", [dict(
            id=1, canal="whatsapp", contacto="59170000001", customer_id=1, region_id=1,
            numero_origen_id=1, estado="bot", atendida_por_id=None, ultimo_entrante_at=moment,
            ultimo_saliente_at=moment, revisada_at=None)])
        self._insert("messaging_mensajeconversacion", [dict(
            id=1, conversacion_id=1, direccion="entrante", origen="contacto", tipo="texto",
            texto="Hola", datos=json.dumps({}), id_externo="wamid.1", clave_unica=None,
            estado="", error_detalle="", enviado_at=None)])
        self._insert("messaging_whatsappmessage", [dict(
            id=1, customer_id=1, charge_id=3, region_id=1, numero_origen_id=1, template_id=1,
            evento="aviso_emitido", destino="59170000001",
            parametros=json.dumps(["Cliente Uno", "300.00"]), header_image_url="",
            estado="leido", intentos=1, wa_message_id="wamid.2", error_codigo="",
            error_detalle="", clave_unica="aviso_emitido:AV-3", enviado_at=moment,
            entregado_at=moment, leido_at=moment)])
        self._insert("messaging_whatsappproof", [dict(
            id=1, customer_id=1, charge_id=3, file="whatsapp-proofs/1/c.pdf",
            mime_type="application/pdf", size_bytes=10, whatsapp_message_id="wamid.3",
            estado="revision", payment_id=None, motivo_rechazo="", simulado=False,
            revisado_at=None, revisado_por_id=None)])
        self._insert("messaging_whatsappsupportcase", [dict(
            id=1, customer_id=1, tipo="ayuda", motivo="Sin señal", estado="nuevo",
            assigned_to_id=None, inbound_message_id="wamid.1", conversacion_id=1,
            resolved_at=None)])
        self._insert("messaging_promocionretencion", [dict(
            id=1, nombre="Un mes a mitad", descripcion="50%", condiciones="", region_id=None,
            vigente_desde=None, vigente_hasta=None, activa=True, orden=1)])
        self._insert("messaging_whatsappsettings", [dict(
            id=1, activo=True, modo_prueba=False, exigir_consentimiento=False,
            api_version="v21.0", waba_id="WABA", app_id="APP", hora_inicio=time(8),
            hora_fin=time(20, 30), dias_recordatorio=3, reintentos_max=3,
            limite_diario_por_cliente=3, horas_silencio_tras_agente=12, intervalo_mora_dias=7,
            max_recordatorios_mora=3)])
        self._insert("messaging_ajustesbotia", [dict(
            id=1, soporte_activo=True, ventas_activo=False, modelo="models/gemini",
            modelo_respaldo="", limite_diario=None, instrucciones_ventas="Ventas",
            instrucciones_soporte="Soporte", quienes_somos="Somos")])
        self._insert("web_sitesettings", [dict(
            id=1, nombre_comercial="MIRABILENET", lema="Internet", descripcion="",
            titulo_portada="", imagen_portada="", frase_portada="", banda_titulo="",
            banda_texto="", telefono="70000000", whatsapp="59170000000", email_ventas="",
            email_soporte="", direccion="", ciudad="Oruro", horario="", facebook="",
            instagram="", tiktok="", mostrar_planes_portada=True, mostrar_planes=True,
            aviso_legal="")])
        self._insert("web_ventaja", [dict(id=1, icono="soporte", titulo="Soporte local",
                                          detalle="", orden=1, activa=True)])
        self._insert("web_service", [dict(
            id=1, slug="internet-hogar", nombre="Internet hogar", resumen="Para casa",
            descripcion="", beneficios="", icono="hogar", destacado=True, orden=1, activo=True)])
        self._insert("web_coveragelocality", [dict(id=1, region_id=1, nombre="Centro",
                                                   detalle="", estado="parcial", orden=1,
                                                   activa=True)])
        self._insert("web_faq", [dict(id=1, pregunta="¿Hay contrato?", respuesta="Sí.",
                                      categoria="pagos", orden=1, activa=True)])
        self._insert("web_documentolegal", [dict(
            id=1, clase="terminos", titulo="Condiciones", resumen="", contenido="# Uso\nTexto",
            version="1.2", vigente_desde=date(2026, 1, 1))])
        self._insert("web_lead", [dict(
            id=1, tipo="cotizacion", nombre="Vecina", telefono="70000003", email="",
            localidad="Centro", region_id=1, servicio_id=1, plan_interes="", mensaje="Quiero",
            estado="nuevo", customer_id=None, nota_interna="", pagina_origen="/planes/",
            source_ip=None, user_agent="")])
        course = dict(region_id=1, nivel="basico", aplicacion="pilotaje", resumen="Primer vuelo",
                      descripcion="", temario="Normativa\nVuelo", requisitos="", incluye="",
                      fecha_fin=None, precio_promocional=None)
        self._insert("aerolab_dronecourse", [
            dict(course, id=1, slug="pilotaje", nombre="Pilotaje básico",
                 fecha_inicio=date(2026, 12, 5), cupos_total=10, precio=800, estado="abierto",
                 publicado=True),
            dict(course, id=2, slug="mapeo", nombre="Mapeo", fecha_inicio=None, cupos_total=0,
                 precio=0, estado="borrador", publicado=False)])
        self._insert("aerolab_courseenrollment", [
            dict(id=1, curso_id=1, nombre="Ana Flores", ci="1234567", telefono="70000004",
                 email="", estado="confirmada", monto_pagado=400),
            dict(id=2, curso_id=1, nombre="Juan", ci="7654321", telefono="70000005", email="",
                 estado="espera", monto_pagado=0)])
        self._insert("pasantias_pasantia", [dict(
            id=1, usuario_id=3, tutor_id=1, institucion="UTO", carrera="Sistemas",
            horas_comprometidas=400, estado="activa")])
        self._insert("pasantias_proyecto", [dict(id=1, nombre="Dron", descripcion="",
                                                 region_id=1)])
        self._insert("pasantias_recurso", [dict(id=1, archivo="pasantias/1/plano.dxf",
                                                nombre_original="plano.dxf")])
        self._insert("pasantias_tarea", [dict(
            id=1, proyecto_id=1, titulo="Soporte del motor", descripcion="Diseñar",
            instrucciones="", region_id=1, fecha_limite=None, pide_archivos=False,
            pide_informe=True, publicada=True)])
        self._insert("pasantias_tarea_recursos", [dict(id=1, tarea_id=1, recurso_id=1)])
        self._insert("pasantias_asignacion", [dict(
            id=1, tarea_id=1, pasantia_id=1, estado="aprobada", entregada_en=moment,
            comentario_pasante="Listo", comentario_tutor="Bien hecho")])
        self._insert("pasantias_itemmarcado", [
            dict(id=1, asignacion_id=1, texto="Medir", orden=1, obligatorio=True, hecho=True),
            dict(id=2, asignacion_id=1, texto="Foto", orden=2, obligatorio=False, hecho=False)])
        self._insert("pasantias_informeavance", [dict(
            id=1, asignacion_id=1, horas_dedicadas=6.5, objetivo="Diseñar el soporte",
            resumen="Hecho", actividades="", herramientas="", parametros="Material: PETG",
            resultados="", validacion="", justificacion="", dificultades="",
            proximos_pasos="", referencias="")])
        self._insert("pasantias_archivo", [dict(id=1, asignacion_id=1,
                                                archivo="pasantias/1/plano.dxf",
                                                nombre_original="soporte.dxf")])
        self._insert("pasantias_comentario", [dict(id=1, asignacion_id=1, autor_id=1,
                                                   texto="Revisa la cota")])

    def test_inventory_messaging_web_aerolab_and_internships(self):
        result = self.Migration._run(self.src)
        ref = self.Migration._ref
        # Inventario
        warehouse = ref("stock.warehouse", "inventory_warehouse", 1)
        self.assertEqual((warehouse.code, warehouse.mirabilenet_branch_id.code), ("ALM1", "MT1"))
        rejected = self._stage(result, "Almacenes")["rechazados"]
        self.assertIn("hasta 5 caracteres", rejected[0][2])
        router = ref("product.template", "inventory_inventoryitem", 1)
        self.assertEqual((router.tracking, router.default_code), ("serial", "RT-1"))
        lot = ref("stock.lot", "inventory_inventoryserial", 2)
        self.assertEqual((lot.mirabilenet_state, lot.mirabilenet_partner_id.name),
                         ("en_cliente", "Cliente Uno"))
        quants = self.env["stock.quant"].search([("location_id", "=", warehouse.lot_stock_id.id)])
        self.assertEqual(sum(quants.mapped("quantity")), 251)
        self.assertTrue(self._stage(result, "Existencias")["notas"])
        # Mensajería
        number = ref("mirabilenet.whatsapp.number", "messaging_branchwhatsappnumber", 1)
        self.assertEqual(number.phone_number_id, "PN-1")
        template = ref("mirabilenet.whatsapp.template", "messaging_messagetemplate", 1)
        self.assertEqual(template.variables, "cliente, saldo")
        self.assertTrue(ref("mirabilenet.payment.qr", "messaging_regionalpaymentqr", 1).image)
        conversation = ref("mirabilenet.conversation", "messaging_conversacion", 1)
        self.assertEqual(conversation.message_ids.text, "Hola",
                         self._stage(result, "Conversaciones"))
        notice = ref("mirabilenet.whatsapp.message", "messaging_whatsappmessage", 1)
        self.assertEqual((notice.state, notice.charge_id.ref), ("leido", "AV-3"))
        proof = ref("mirabilenet.whatsapp.proof", "messaging_whatsappproof", 1)
        self.assertEqual((proof.state, proof.charge_id.ref, proof.file_name),
                         ("revision", "AV-3", "c.pdf"))
        self.assertEqual(ref("mirabilenet.support.case", "messaging_whatsappsupportcase",
                             1).conversation_id, conversation)
        settings = self.env["mirabilenet.whatsapp.settings"]._load()
        self.assertEqual((settings.active_messaging, settings.hour_end, settings.waba_id),
                         (False, 20.5, "WABA"))
        self.assertEqual(self.env["mirabilenet.bot.settings"]._load().about_us, "Somos")
        # Web
        self.assertEqual(self.env["mirabilenet.web.settings"]._load().city, "Oruro")
        self.assertEqual(ref("mirabilenet.web.service", "web_service", 1).slug, "internet-hogar")
        self.assertEqual(ref("mirabilenet.web.coverage", "web_coveragelocality", 1).state,
                         "parcial")
        self.assertEqual(ref("mirabilenet.web.legal", "web_documentolegal", 1).version, "1.2")
        lead = ref("crm.lead", "web_lead", 1)
        self.assertEqual((lead.mirabilenet_kind, lead.mirabilenet_web_service_id.slug,
                          lead.mirabilenet_origin), ("cotizacion", "internet-hogar", "web:/planes/"))
        # AeroLab
        course = ref("event.event", "aerolab_dronecourse", 1)
        self.assertEqual((course.website_published, course.mirabilenet_date_confirmed,
                          course.event_ticket_ids.price), (True, True, 800))
        draft = ref("event.event", "aerolab_dronecourse", 2)
        self.assertEqual((draft.website_published, draft.mirabilenet_date_confirmed),
                         (False, False))
        confirmed = ref("event.registration", "aerolab_courseenrollment", 1)
        self.assertEqual((confirmed.state, confirmed.registration_answer_ids.value_text_box),
                         ("open", "1234567"))
        self.assertEqual(ref("event.registration", "aerolab_courseenrollment", 2).state, "draft")
        # Pasantías
        employee = ref("hr.employee", "pasantias_pasantia", 1)
        self.assertEqual((employee.employee_type, employee.user_id.login,
                          employee.mirabilenet_institution), ("trainee", "m_pasante", "UTO"))
        task = ref("project.task", "pasantias_asignacion", 1)
        self.assertEqual((task.state, task.stage_id,
                          task.user_ids), ("03_approved",
                                           self.env.ref("mirabilenet_pasantias.stage_approved"),
                                           employee.user_id))
        self.assertEqual({c.name: c.state for c in task.child_ids},
                         {"Medir": "1_done", "Foto": "01_in_progress"})
        self.assertEqual(task.mirabilenet_report_id.goal, "Diseñar el soporte")
        self.assertEqual(task.mirabilenet_report_id.tutor_comment, "Bien hecho")
        files = self.env["ir.attachment"].search([("res_model", "=", "project.task"),
                                                  ("res_id", "=", task.id)])
        self.assertEqual(sorted(files.mapped("name")), ["plano.dxf", "soporte.dxf"])
        self.assertIn("Revisa la cota", " ".join(task.message_ids.mapped("body")))
        # Controles nuevos
        labels = {c["control"]: c for c in result["controles"]}
        self.assertTrue(labels["Unidades en almacenes"]["coincide"])
        self.assertTrue(labels["Comprobantes revision"]["coincide"])

    def test_a_partial_run_only_checks_its_stages(self):
        result = self.Migration._run(self.src, stages=["organization"])
        self.assertEqual(result["controles"], [])

    def test_a_missing_proof_file_stops_the_migration(self):
        os.remove(os.path.join(self.private, "whatsapp-proofs/1/c.pdf"))
        with self.assertRaisesRegex(MigrationMismatch, "no disponible en la copia de private_media"):
            self.Migration._run(self.src)

    def _stage(self, result, name):
        return next(s for s in result["etapas"] if s["etapa"] == name)

    # ------------------------------------------------------------------
    def test_migration_creates_everything_with_old_ids(self):
        result = self.Migration._run(self.src)
        ref = self.Migration._ref
        region = ref("mirabilenet.region", "core_region", 1)
        self.assertEqual((region.code, region.hora_corte, region.currency_id.name),
                         ("M-T", 9.5, "BOB"))
        self.assertEqual(ref("mirabilenet.node", "core_node", 1).region_id, region)
        user = ref("res.users", "core_user", 1)
        self.assertEqual((user.login, user.mirabilenet_role, user.mirabilenet_region_id),
                         ("m_admin", "admin_regional", region))
        self.assertFalse(user.password, "las contraseñas no se migran")
        users = self._stage(result, "Usuarios")
        self.assertEqual(users["rechazados"][0][1], 2)
        self.assertIn("rol de cliente", users["rechazados"][0][2])
        customer = ref("res.partner", "crm_customer", 1)
        self.assertEqual((customer.mirabilenet_code, customer.mirabilenet_state, customer.user_id),
                         ("MT-0001", "activo", user))
        self.assertEqual(ref("res.partner", "crm_customercontact", 1).parent_id, customer)
        customers = self._stage(result, "Clientes")
        self.assertIn("región 99 sin migrar", customers["rechazados"][0][2])
        router = ref("mirabilenet.router", "isp_router", 1)
        self.assertEqual((router.wg_ip, router.state, router.has_credentials),
                         ("10.250.239.10", "conectado", False))
        self.assertTrue(self._stage(result, "Routers")["notas"])
        service = ref("mirabilenet.service", "isp_service", 1)
        self.assertEqual((service.state, service.monthly_price, service.router_id),
                         ("activo", 300, router))
        self.assertFalse(service.transition_ids, "migrar no manda órdenes a la red")
        self.assertTrue(self._stage(result, "Cuentas PPPoE")["notas"])
        # Avisos: tres pasan, el anulado se reporta.
        charges = self._stage(result, "Avisos de cobro → facturas")
        self.assertEqual(charges["migrados"], 3)
        self.assertIn("anulado", charges["rechazados"][0][2])
        paid, partial, overdue = (ref("account.move", "billing_charge", i) for i in (1, 2, 3))
        self.assertEqual((paid.ref, paid.amount_residual), ("AV-1", 0))
        self.assertEqual(partial.amount_residual, 100)
        self.assertEqual(overdue.amount_residual, 300)
        self.assertEqual(overdue.invoice_date_due, date(2026, 10, 10))
        payments = self.env["account.payment"].search([("partner_id", "=", customer.id)])
        self.assertEqual(sorted(payments.mapped("amount")), [50, 200, 300])
        self.assertTrue(any("MN-MT1-C1-000045" in (p.memo or "") for p in payments))
        self.assertFalse(service.transition_ids, "un pago migrado no pide reactivar")
        # Las sumas de control coinciden.
        self.assertTrue(all(c["coincide"] for c in result["controles"]))
        labels = {c["control"]: c for c in result["controles"]}
        self.assertEqual(Decimal(labels["Saldo total adeudado"]["odoo"]), Decimal("400"))
        self.assertEqual(Decimal(labels["Cobrado en 2026-09"]["odoo"]), Decimal("550"))
        self.assertIn("Informe de migración", self.Migration._report_markdown(result))

    def test_running_twice_duplicates_nothing(self):
        self.Migration._run(self.src)
        again = self.Migration._run(self.src)
        self.assertEqual(sum(s["migrados"] for s in again["etapas"]), 0)
        self.assertEqual(self._stage(again, "Clientes")["ya_migrados"], 1)
        self.assertEqual(self.env["res.partner"].search_count(
            [("mirabilenet_code", "=", "MT-0001")]), 1)

    def test_a_control_mismatch_stops_and_shows_the_difference(self):
        self.Migration._run(self.src)
        self.env.cr.execute("UPDATE %s.billing_charge SET saldo = 250 WHERE id = 3" % SCHEMA)
        with self.assertRaises(MigrationMismatch) as caught:
            self.Migration._run(self.src)
        self.assertIn("Saldo total adeudado: origen 350", str(caught.exception))

    def test_guards(self):
        with self.assertRaises(UserError):
            self.Migration.with_user(self.env.ref("base.user_admin"))._run(self.src)
        with self.assertRaises(SourceError):
            SourceReader(self.env.cr, "mal; DROP")
        self.env.cr.execute("ALTER TABLE %s.core_zone DROP COLUMN sector" % SCHEMA)
        with self.assertRaisesRegex(SourceError, "sector"):
            self.Migration._run(self.src)

    def test_contracts_start_on_the_cutover_date(self):
        result = self.Migration._run(self.src)
        self.assertTrue(self._stage(result, "Contratos de cobro")["notas"])
        service = self.Migration._ref("mirabilenet.service", "isp_service", 1)
        self.assertFalse(service.contract_id)
        self.Migration.with_context(mirabilenet_billing_start="2026-11-01")._run(self.src)
        line = service.contract_id.contract_line_ids
        self.assertEqual((line.date_start, line.price_unit), (date(2026, 11, 1), 300))
