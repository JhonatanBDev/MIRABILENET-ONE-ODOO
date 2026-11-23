import os
import time
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.mirabilenet_isp.isp import vault
from odoo.addons.mirabilenet_whatsapp.whatsapp.gateway import FakeMetaGateway


@tagged("mirabilenet", "post_install", "-at_install")
class TestCotizadorWhatsapp(TransactionCase):
    """Todos los datos son ficticios; los recargos son de prueba."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.startClassPatcher(patch.dict(os.environ, {vault.ENV_VAR: "clave-de-prueba"}))
        cls.env["ir.config_parameter"].set_param("mirabilenet.meta_gateway", "fake")
        FakeMetaGateway.reset()
        cls.region = cls.env["mirabilenet.region"].create(
            {"code": "C-N", "name": "Norte cotizador", "wg_region_id": 43})
        cls.branch = cls.env["mirabilenet.branch"].create(
            {"region_id": cls.region.id, "code": "CN1", "name": "Central cotizador"})
        cls.settings = cls.env["mirabilenet.whatsapp.settings"]._load()
        cls.settings.write({"active_messaging": True, "test_mode": False, "waba_id": "WABA-C",
                            "access_token": "token-meta", "app_secret": "secreto-app",
                            "webhook_verify_token": "verificame", "hour_start": 0,
                            "hour_end": 24, "require_consent": False})
        cls.number = cls.env["mirabilenet.whatsapp.number"].create(
            {"branch_id": cls.branch.id, "phone_number_id": "PN-C",
             "display_number": "+59170000019"})
        cls.seller = cls._user("c_vendedor", "vendedor", "70000021")
        cls.tech = cls._user("c_tecnico", "tecnico", "70000022")
        group = cls.env.ref("mirabilenet_cotizador.group_mirabilenet_cot_user")
        (cls.seller | cls.tech).write({"group_ids": [(4, group.id)]})
        cls.outsider = cls._user("c_cajero", "cajero", "70000023")
        Markup = cls.env["mirabilenet.cot.markup"]
        Markup.search([]).unlink()
        for category in ("CAMARAS IP", "GRABADORES IP", "DISCOS DUROS Y SERVIDORES",
                         "CABLES DE RED"):
            Markup.create({"kind": "categoria", "category": category, "markup": 20})
        cls.products = cls.env["product.template"]
        for sku, name, cost, category in (
                ("W-CAM-B", "CAMARA IP BULLET 4MP *PoE *IP67 EXTERIOR", 300, "CAMARAS IP"),
                ("W-CAM-D", "CAMARA IP DOMO 4MP *PoE *IP67", 280, "CAMARAS IP"),
                ("W-NVR", "GRABADOR NVR 8CH *8 PUERTOS POE *1 HDD HASTA 8TB", 600,
                 "GRABADORES IP"),
                ("W-HDD4", "DISCO DURO PURPLE 4TB", 650, "DISCOS DUROS Y SERVIDORES"),
                ("W-UTP", "CABLE UTP CAT6 EXT 305 METROS", 900, "CABLES DE RED")):
            cls.products |= cls.env["product.template"].create({
                "name": name, "type": "consu", "standard_price": cost, "sale_ok": True,
                "mirabilenet_cot_sku": sku, "mirabilenet_cot_category": category,
                "mirabilenet_cot_brand": "DAHUA", "mirabilenet_cot_cost_at": fields.Datetime.now(),
                "mirabilenet_cot_stock": {"La Paz": 30}, "mirabilenet_cot_stock_total": 30,
                "mirabilenet_cot_offer_bot": True})
        cls.kit = cls.env.ref("mirabilenet_cotizador.kit_casa_4")
        cls.kit.offer_bot = True
        cls.Api = cls.env["mirabilenet.n8n.api"]
        cls.Delivery = cls.env["mirabilenet.cot.delivery"]

    @classmethod
    def _user(cls, login, role, whatsapp):
        user = new_test_user(cls.env, login, groups="base.group_user", name=login.upper())
        user.write({"mirabilenet_role": role, "mirabilenet_region_id": cls.region.id,
                    "mirabilenet_whatsapp": whatsapp})
        return user

    def setUp(self):
        super().setUp()
        FakeMetaGateway.reset()

    def _incoming(self, number, **message):
        payload = dict({"from": number, "id": "wamid.C%s" % time.monotonic_ns(),
                        "timestamp": str(int(time.time()))}, **message)
        return self.env["mirabilenet.conversation"]._process_meta_incoming(payload, "PN-C")

    def _prospect(self, number="70000031"):
        self._incoming(number, type="text", text={"body": "Quiero cámaras para mi casa"})
        return self.env["mirabilenet.conversation"].search(
            [("contact", "=", "591" + number)], limit=1)

    def _sent(self):
        self.env["mirabilenet.conversation.message"]._dispatch_pending() if hasattr(
            self.env["mirabilenet.conversation.message"], "_dispatch_pending") else None
        self.env["mirabilenet.staff.notice"]._cron_dispatch()
        self.Delivery._cron_dispatch()
        sent = list(FakeMetaGateway.sent)
        FakeMetaGateway.sent.clear()
        return sent

    # ------------------------------------------------------------------
    def test_bot_tools_list_kits_and_products(self):
        conversation = self._prospect()
        status, body = self.Api.conversation_kits(conversation.id)
        self.assertEqual(status, 200)
        self.assertIn("casa_4", [k["codigo"] for k in body["kits"]])
        self.assertIn("La Paz", body["ciudades"])
        status, body = self.Api.conversation_products(conversation.id, {"buscar": "domo"})
        self.assertEqual(status, 200)
        self.assertEqual(len(body["equipos"]), 1)
        item = body["equipos"][0]
        self.assertEqual(item["precio"], 340)  # 280 × 1,20 = 336 → 340: lo pone el motor
        self.assertTrue(item["hay_en_la_ciudad"])
        self.assertNotIn("costo", item)
        self.assertEqual(self.Api.conversation_kits(0)[0], 404)

    def test_bot_sends_the_quotation_directly(self):
        conversation = self._prospect()
        status, body = self.Api.conversation_quotation(conversation.id, {
            "kit": "casa_4", "ciudad": "la paz", "nombre": "Juan Ficticio", "mensaje_id": "m1"})
        self.assertEqual(status, 201, body)
        self.assertTrue(body["enviada"])
        order = self.env["sale.order"].search([("name", "=", body["numero"])])
        self.assertEqual(order.mirabilenet_cot_origin, "bot")
        self.assertEqual(order.mirabilenet_cot_stage, "enviada")
        self.assertEqual(order.partner_id.name, "Juan Ficticio")
        self.assertEqual(body["total"], round(order.mirabilenet_cot_total, 2))
        message = self.env["mirabilenet.conversation.message"].search(
            [("conversation_id", "=", conversation.id), ("direction", "=", "saliente")])
        self.assertEqual(message.kind, "documento")
        self.assertIn(order.name, message.text)
        self.assertNotIn("Costo", message.text)
        # Sin kit ni pedido, o sin nombre, no cotiza.
        self.assertEqual(self.Api.conversation_quotation(conversation.id, {"nombre": "X Y"})[0],
                         400)
        self.assertEqual(self.Api.conversation_quotation(conversation.id, {"kit": "casa_4"})[0],
                         400)
        self.assertEqual(self.Api.conversation_quotation(
            conversation.id, {"kit": "no_existe", "nombre": "Juan Ficticio"})[0], 404)

    def test_bot_quotation_with_alerts_waits_for_a_seller(self):
        conversation = self._prospect("70000032")
        self.products.write({"mirabilenet_cot_stock": {"La Paz": 0},
                             "mirabilenet_cot_stock_total": 0})
        status, body = self.Api.conversation_quotation(conversation.id, {
            "kit": "casa_4", "ciudad": "La Paz", "nombre": "Ana Ficticia"})
        if status == 409:   # sin existencias el motor puede no encontrar equipos: tampoco sale
            self.assertEqual(body["codigo"], "no_se_pudo_cotizar")
            return
        self.assertEqual(status, 202, body)
        self.assertFalse(body["enviada"])
        self.assertNotIn("total", body)
        order = self.env["sale.order"].search([("name", "=", body["numero"])])
        self.assertEqual(order.mirabilenet_cot_stage, "borrador")
        self.assertFalse(self.env["mirabilenet.conversation.message"].search(
            [("conversation_id", "=", conversation.id), ("direction", "=", "saliente")]))
        notice = self.env["mirabilenet.staff.notice"].search(
            [("kind", "=", "cotizacion_revisar")])
        self.assertEqual(notice.user_id, self.seller)
        self.assertEqual(notice.parameters["referencia"], order.name)

    def test_worker_quotes_and_sends_to_the_customer(self):
        Inbox = self.env["mirabilenet.staff.inbox"]
        record = Inbox._enqueue(self.tech, "cotiza casa 4 para Juan Ficticio 70000041")
        status, body = Inbox._apply_result({
            "mensaje_id": record.id, "accion": "cotizar", "kit": "casa_4", "ciudad": "La Paz",
            "cliente_nombre": "Juan Ficticio", "cliente_telefono": "70000041"})
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"])
        order = self.env["sale.order"].search([("name", "=", body["numero"])])
        self.assertEqual(order.mirabilenet_cot_origin, "trabajador")
        self.assertEqual(order.mirabilenet_cot_requester_id, self.tech)
        self.assertEqual(order.mirabilenet_cot_stage, "borrador")
        sent = self._sent()
        document = [m for m in sent if m["kind"] == "session" and m["tipo"] == "documento"]
        buttons = [m for m in sent if m["kind"] == "session" and m["tipo"] == "botones"]
        self.assertEqual(document[0]["destino"], "59170000022")
        self.assertEqual(buttons[0]["contenido"]["botones"][0]["id"], "mnc:%d:enviar" % order.id)
        # Otra persona no puede enviar una cotización ajena.
        self._incoming(self.seller.mirabilenet_whatsapp, type="text",
                       text={"body": "enviar %s" % order.name})
        self.assertEqual(order.mirabilenet_cot_stage, "borrador")
        # El que la pidió aprieta «Enviar al cliente»: se aprueba y sale con plantilla, porque
        # el cliente no escribió en las últimas 24 horas.
        self._incoming(self.tech.mirabilenet_whatsapp, type="interactive", interactive={
            "type": "button_reply",
            "button_reply": {"id": "mnc:%d:enviar" % order.id, "title": "Enviar al cliente"}})
        self.assertEqual(order.mirabilenet_cot_stage, "aprobada")
        self.assertEqual(order.mirabilenet_cot_approved_by, self.tech)
        sent = self._sent()
        template = [m for m in sent if m["kind"] == "template"]
        self.assertEqual(template[0]["plantilla"], "cotizacion")
        self.assertEqual(template[0]["destino"], "59170000041")
        self.assertTrue(template[0]["header_document"]["id"])
        self.assertIn(order.name, template[0]["parametros"])
        self.assertEqual(order.mirabilenet_cot_stage, "enviada")

    def test_worker_without_permission_or_data(self):
        Inbox = self.env["mirabilenet.staff.inbox"]
        record = Inbox._enqueue(self.outsider, "cotiza casa 4")
        status, body = Inbox._apply_result({"mensaje_id": record.id, "accion": "cotizar",
                                            "kit": "casa_4", "cliente_nombre": "Juan Ficticio"})
        self.assertEqual(body["resultado"], "sin_permiso")
        record = Inbox._enqueue(self.tech, "cotiza casa 4")
        status, body = Inbox._apply_result({"mensaje_id": record.id, "accion": "cotizar",
                                            "kit": "casa_4"})
        self.assertEqual(body["resultado"], "falta_cliente")
        self.assertEqual(record.state, "atendido")
        # Las demás acciones siguen yendo a lo de siempre.
        record = Inbox._enqueue(self.tech, "hola")
        self.assertEqual(Inbox._apply_result({"mensaje_id": record.id, "accion": "ninguna",
                                              "respuesta": "Hola"})[0], 200)

    def test_send_from_odoo_inside_the_open_window(self):
        conversation = self._prospect("70000051")
        partner = self.env["res.partner"].create({"name": "Cliente Ficticio",
                                                  "phone": "70000051"})
        order = self.env["mirabilenet.cot.engine"].create_from_kit(self.kit, "La Paz", partner)
        order.with_user(self.seller).action_mirabilenet_cot_whatsapp_customer()
        self.assertEqual(order.mirabilenet_cot_stage, "aprobada")
        sent = self._sent()
        document = [m for m in sent if m["kind"] == "session" and m["tipo"] == "documento"]
        self.assertEqual(document[0]["destino"], conversation.contact)
        self.assertFalse([m for m in sent if m["kind"] == "template"])
        self.assertEqual(order.mirabilenet_cot_stage, "enviada")
        self.assertEqual(order.mirabilenet_cot_delivery_ids.channel, "conversación abierta")
