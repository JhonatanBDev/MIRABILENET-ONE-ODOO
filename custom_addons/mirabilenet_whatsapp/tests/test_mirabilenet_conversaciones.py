import base64
import hashlib
import hmac
import json
import os
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged

from ..whatsapp import content, n8n
from ..whatsapp.content import SendRejected
from ..whatsapp.gateway import FakeMetaGateway
from ..whatsapp.n8n import FakeN8NClient
from .test_mirabilenet_whatsapp import PNG, TODAY, WhatsappCommon

PDF = b"%PDF-1.4 comprobante de prueba"
JPG = b"\xff\xd8\xff\xe0 comprobante"
ENV = {n8n.TOKEN_ENV: "token-de-n8n", n8n.SECRET_ENV: "secreto-de-firma-de-32-caracteres!!"}


@tagged("mirabilenet", "post_install", "-at_install")
class TestContentAndSigning(TransactionCase):

    def test_validate_content(self):
        self.assertEqual(content.validate_content("texto", {"texto": " Hola\x00 "}),
                         {"texto": "Hola"})
        buttons = content.validate_content("botones", {
            "texto": "¿En qué le ayudo?", "pie": "MIRABILENET",
            "botones": [{"id": "deuda", "titulo": "Ver mi deuda"}]})
        self.assertEqual(buttons["botones"], [{"id": "deuda", "titulo": "Ver mi deuda"}])
        listing = content.validate_content("lista", {"texto": "Elija", "lista": {
            "boton": "Ver avisos", "secciones": [{"titulo": "Avisos", "filas": [
                {"id": "a1", "titulo": "AV-1", "descripcion": "Bs 100"}]}]}})
        self.assertEqual(listing["lista"]["secciones"][0]["filas"][0]["descripcion"], "Bs 100")
        bad = [
            ("texto", {}), ("texto", {"texto": "x" * 4097}), ("imagen", {"texto": "x"}),
            ("botones", {"texto": "x", "botones": []}),
            ("botones", {"texto": "x", "botones": [{"id": "a", "titulo": "t"}] * 4}),
            ("botones", {"texto": "x", "botones": [{"id": "a", "titulo": "t" * 21}]}),
            ("botones", {"texto": "x", "botones": [{"id": "a", "titulo": "t"},
                                                   {"id": "a", "titulo": "u"}]}),
            ("botones", {"texto": "x" * 1025, "botones": [{"id": "a", "titulo": "t"}]}),
            ("lista", {"texto": "x"}),
            ("lista", {"texto": "x", "lista": {"boton": "b", "secciones": [
                {"filas": [{"id": str(i), "titulo": "f"} for i in range(11)]}]}}),
            ("texto", "no es un objeto"),
        ]
        for kind, data in bad:
            with self.assertRaises(ValueError, msg="%s %r" % (kind, data)):
                content.validate_content(kind, data)

    def test_normalize_meta_incoming(self):
        norm = content.normalize_meta_incoming
        self.assertEqual(norm({"type": "text", "text": {"body": " Hola "}}), ("texto", "Hola", {}))
        self.assertEqual(
            norm({"type": "interactive", "interactive": {
                "button_reply": {"id": "deuda", "title": "Ver mi deuda"}}}),
            ("respuesta", "Ver mi deuda", {"opcion_id": "deuda"}))
        self.assertEqual(norm({"type": "image", "image": {"mime_type": "image/jpeg",
                                                         "caption": "pago"}}),
                         ("imagen", "pago", {"mime": "image/jpeg"}))
        kind, _text, data = norm({"type": "location", "location": {
            "latitude": "-17.96", "longitude": "-67.11", "name": "Casa"}})
        self.assertEqual((kind, data["latitud"], data["nombre"]), ("ubicacion", -17.96, "Casa"))
        self.assertEqual(norm({"type": "location", "location": {"latitude": 200}})[0], "otro")
        self.assertEqual(norm({"type": "sticker"}), ("otro", "", {"tipo_meta": "sticker"}))

    def test_real_type(self):
        self.assertEqual(content.real_type(PDF), "application/pdf")
        self.assertEqual(content.real_type(JPG), "image/jpeg")
        self.assertIsNone(content.real_type(b"<html>"))
        self.assertEqual(content.safe_file_name('..\\mal"o.exe', "image/png"), "mal_o.png")

    def test_event_signature_matches_what_n8n_validates(self):
        secret = ENV[n8n.SECRET_ENV]
        payload = {"evento": "mensaje_entrante", "mensaje": {"texto": "¡Hola!"}}
        body = n8n.encode_body(payload)
        self.assertEqual(body, '{"evento":"mensaje_entrante","mensaje":{"texto":"¡Hola!"}}'
                         .encode())
        headers = n8n.headers_for(secret, body, now=1_800_000_000)
        self.assertEqual(headers["X-Mirabilenet-Signature"], "sha256=" + hmac.new(
            secret.encode(), body, hashlib.sha256).hexdigest())
        token = headers["Authorization"][len("Bearer "):]
        head, claims, signature = token.split(".")

        def decode(part):
            return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))

        self.assertEqual(decode(head), {"alg": "HS256", "typ": "JWT"})
        self.assertEqual(decode(claims), {
            "iss": "mirabilenet", "iat": 1_800_000_000, "exp": 1_800_000_120,
            "sha256": hashlib.sha256(body).hexdigest()})
        expected = base64.urlsafe_b64encode(hmac.new(
            secret.encode(), ("%s.%s" % (head, claims)).encode(), hashlib.sha256).digest()
        ).rstrip(b"=").decode()
        self.assertEqual(signature, expected)

    def test_token_and_url_checks(self):
        with patch.dict(os.environ, ENV):
            self.assertTrue(n8n.token_matches("Bearer token-de-n8n"))
            self.assertTrue(n8n.token_matches("token-de-n8n"))
            for bad in ("", "Bearer otro", "Bearer ", None):
                self.assertFalse(n8n.token_matches(bad))
        with patch.dict(os.environ, clear=True):
            self.assertFalse(n8n.token_matches("Bearer "), "sin token configurado, nadie entra")
            self.assertFalse(n8n.token_matches("Bearer token-de-n8n"))
        self.assertTrue(n8n.check_url("https://n8n.example/webhook/x"))
        self.assertTrue(n8n.check_url("http://n8n:5678/webhook/mirabilenet-entrante"))
        for bad in ("http://evil.example/webhook", "ftp://n8n/x", ""):
            with self.assertRaises(n8n.N8NError):
                n8n.check_url(bad)


class ConversationCommon(WhatsappCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.startClassPatcher(patch.dict(os.environ, ENV))
        Param = cls.env["ir.config_parameter"]
        Param.set_param("mirabilenet.n8n_client", "fake")
        Param.set_param("mirabilenet.n8n_inbound_webhook_url",
                        "http://n8n:5678/webhook/mirabilenet-entrante")
        cls.api = cls.env["mirabilenet.n8n.api"]
        cls.Conversation = cls.env["mirabilenet.conversation"]
        cls.cajero_n = cls._user("t_cajero_n", "cajero", cls.norte)

    def setUp(self):
        super().setUp()
        FakeN8NClient.reset()

    def _meta_text(self, text, origin="59171006044", wamid="wamid.IN-1", **extra):
        message = {"from": origin, "id": wamid, "type": "text", "text": {"body": text},
                   "timestamp": str(int(fields.Datetime.now().timestamp()))}
        message.update(extra)
        return message

    def _incoming(self, text="Hola", **kw):
        self.Conversation._process_meta_incoming(self._meta_text(text, **kw), "PN-N")
        return self.Conversation.search([("channel", "=", "whatsapp")], order="id desc",
                                        limit=1)

    def _deliver(self):
        self.env["mirabilenet.n8n.event"]._cron_deliver()
        return FakeN8NClient.received


@tagged("mirabilenet", "post_install", "-at_install")
class TestConversations(ConversationCommon):

    def test_incoming_is_registered_and_forwarded(self):
        conversation = self._incoming("Hola, ¿cuánto debo?")
        self.assertEqual((conversation.contact, conversation.partner_id, conversation.region_id,
                          conversation.number_id, conversation.state),
                         ("59171006044", self.cliente, self.norte, self.number_n, "bot"))
        self.assertTrue(conversation.window_open)
        message = conversation.message_ids
        received = self._deliver()
        self.assertEqual(len(received), 1)
        event = received[0]["payload"]
        self.assertEqual(received[0]["url"], "http://n8n:5678/webhook/mirabilenet-entrante")
        self.assertEqual(sorted(event), sorted([
            "evento", "mensaje_id", "canal", "conversacion", "contacto", "mensaje",
            "manejado_por_sistema", "ia", "comprobante", "recibido_at"]))
        self.assertEqual((event["evento"], event["mensaje_id"], event["canal"]),
                         ("mensaje_entrante", message.id, "whatsapp"))
        self.assertEqual(event["conversacion"]["id"], conversation.id)
        self.assertEqual(event["conversacion"]["estado"], "bot")
        self.assertTrue(event["conversacion"]["ventana_hasta"].endswith("-04:00"))
        self.assertEqual(event["contacto"], {"telefono": "59171006044", "es_cliente": True})
        self.assertEqual(event["mensaje"], {"tipo": "texto", "texto": "Hola, ¿cuánto debo?",
                                            "opcion_id": "", "ubicacion": None, "mime": ""})
        self.assertIsNone(event["manejado_por_sistema"])
        self.assertEqual(event["ia"], {"soporte": True, "ventas": True,
                                       "modelo": "models/gemini-flash-lite-latest",
                                       "disponible": True})
        # El evento no lleva datos del cliente: ni nombre ni código.
        self.assertNotIn("Juan", json.dumps(event))
        self.assertNotIn(self.cliente.mirabilenet_code, json.dumps(event))

    def test_repeated_meta_message_is_not_duplicated(self):
        self._incoming("Hola")
        conversation = self._incoming("Hola")
        self.assertEqual(len(conversation.message_ids), 1)

    def test_prospect_gets_a_conversation_too(self):
        conversation = self._incoming("Quiero internet", origin="59179998888", wamid="w-p")
        self.assertFalse(conversation.partner_id)
        self.assertEqual(conversation.region_id, self.norte, "la región del número que recibió")
        self.assertFalse(self._deliver()[0]["payload"]["contacto"]["es_cliente"])

    def test_opt_out_word_is_handled_before_the_bot(self):
        self._incoming("BAJA")
        self.assertTrue(self.env["mirabilenet.whatsapp.optout"].search(
            [("partner_id", "=", self.cliente.id)]))
        self.assertEqual(self._deliver()[0]["payload"]["manejado_por_sistema"], "baja")

    def test_delivery_failures_raise_an_alert(self):
        self._incoming("Hola")
        FakeN8NClient.failures.extend(["403"] * 4)
        event = self.env["mirabilenet.n8n.event"].search([], limit=1)
        for expected in ("pendiente", "pendiente", "pendiente", "fallido"):
            self.env["mirabilenet.n8n.event"]._cron_deliver()
            self.assertEqual(event.state, expected)
        alert = self.env["mirabilenet.integration.alert"].search([])
        self.assertIn("no recibió respuesta", alert.message)
        self.assertEqual(self.env["mirabilenet.n8n.event"]._cron_deliver(), 0)

    def test_nothing_is_forwarded_without_n8n(self):
        self.env["ir.config_parameter"].set_param("mirabilenet.n8n_inbound_webhook_url", "")
        conversation = self._incoming("ayuda por favor")
        self.assertFalse(self.env["mirabilenet.n8n.event"].search([]))
        # Sin n8n, pedir ayuda abre la solicitud directo y pausa el chat.
        case = self.env["mirabilenet.support.case"].search([])
        self.assertEqual((case.kind, case.partner_id), ("ayuda", self.cliente))
        self.assertEqual(conversation.state, "humano")

    def test_cancel_phrase_goes_to_the_bot_when_support_is_on(self):
        self._incoming("Quiero cancelar mi servicio")
        self.assertFalse(self.env["mirabilenet.support.case"].search([]))
        self.env["mirabilenet.bot.settings"]._load().sudo().support_on = False
        conversation = self._incoming("Quiero cancelar mi servicio", wamid="w-2")
        self.assertEqual(self.env["mirabilenet.support.case"].search([]).kind, "baja_servicio")
        self.assertEqual(conversation.state, "humano")

    def test_bot_reply_rules(self):
        conversation = self._incoming("Hola")
        status, body = self.api.messages({
            "conversacion_id": conversation.id, "tipo": "texto", "clave": "eco:1",
            "contenido": {"texto": "Hola, Juan", "modelo": "models/gemini-flash-lite-latest"}})
        self.assertEqual((status, body["estado"], body["duplicado"]), (201, "pendiente", False))
        again = self.api.messages({"conversacion_id": conversation.id, "tipo": "texto",
                                   "clave": "eco:1", "contenido": {"texto": "Hola, Juan"}})
        self.assertEqual((again[0], again[1]["id"], again[1]["duplicado"]),
                         (200, body["id"], True))
        message = self.env["mirabilenet.conversation.message"].browse(body["id"])
        self.assertEqual(message.data["modelo"], "models/gemini-flash-lite-latest")
        self.env["mirabilenet.conversation.message"]._cron_dispatch()
        self.assertEqual(message.state, "enviado")
        sent = FakeMetaGateway.sent[-1]
        self.assertEqual((sent["kind"], sent["destino"], sent["tipo"],
                          sent["contenido"]["texto"]),
                         ("session", "59171006044", "texto", "Hola, Juan"))
        self.assertTrue(conversation.last_outgoing_at)

        def reply(key="eco:2", **extra):
            data = {"conversacion_id": conversation.id, "tipo": "texto", "clave": key,
                    "contenido": {"texto": "x"}}
            data.update(extra)
            return self.api.messages(data)

        self.assertEqual(reply(conversacion_id=999999)[0], 404)
        self.assertEqual(reply(conversacion_id="abc")[0], 404)
        self.assertEqual(reply(tipo="video")[0], 400)
        self.assertEqual(reply(clave="")[1]["codigo"], "falta_clave")
        other = self._incoming("Hola", origin="59179998888", wamid="w-otro")
        self.assertEqual(self.api.messages({
            "conversacion_id": other.id, "tipo": "texto", "clave": "eco:1",
            "contenido": {"texto": "x"}})[1]["codigo"], "clave_en_uso")
        conversation.sudo().state = "humano"
        self.assertEqual(reply()[1]["codigo"], "atiende_una_persona")
        conversation.sudo().state = "cerrada"
        self.assertEqual(reply()[1]["codigo"], "cerrada")
        conversation.sudo().state = "bot"
        self.settings.active_messaging = False
        self.assertEqual(reply()[1]["codigo"], "mensajeria_apagada")
        self.settings.active_messaging = True
        conversation.sudo().number_id = False
        self.assertEqual(reply()[1]["codigo"], "sin_numero")
        conversation.sudo().number_id = self.number_n
        conversation.sudo().last_incoming_at = fields.Datetime.now() - timedelta(hours=25)
        self.assertEqual(reply(), (409, {
            "codigo": "fuera_de_ventana",
            "detail": "Pasaron mas de 24 horas desde el ultimo mensaje del contacto: solo se "
                      "puede escribir con una plantilla."}))
        conversation.sudo().last_incoming_at = fields.Datetime.now()
        self.env["mirabilenet.whatsapp.optout"].create({"partner_id": self.cliente.id})
        self.assertEqual(reply()[1]["codigo"], "dado_de_baja")

    def test_bot_hourly_limit(self):
        conversation = self._incoming("Hola")
        for index in range(content.BOT_HOURLY_LIMIT):
            conversation._enqueue_outgoing("texto", {"texto": "r"}, "k:%d" % index)
        with self.assertRaises(SendRejected) as caught:
            conversation._enqueue_outgoing("texto", {"texto": "r"}, "k:de-mas")
        self.assertEqual(caught.exception.code, "limite_por_hora")

    def test_handoff_pauses_the_bot_and_reuses_the_case(self):
        conversation = self._incoming("No tengo internet")
        status, body = self.api.conversation_handoff(
            conversation.id, {"motivo": "Sin señal", "mensaje_id": 812})
        self.assertEqual((status, body["estado"], body["duplicado"]), (201, "nuevo", False))
        case = self.env["mirabilenet.support.case"].browse(body["caso_id"])
        self.assertEqual((case.kind, case.reason, case.conversation_id),
                         ("ayuda", "Sin señal", conversation))
        self.assertEqual(conversation.state, "humano")
        notice = conversation.message_ids.filtered(lambda m: m.direction == "saliente")
        self.assertEqual(notice.text, content.HANDOFF_NOTICE, "el aviso sale antes de pausar")
        again = self.api.conversation_handoff(conversation.id, {"mensaje_id": 813})
        self.assertEqual((again[0], again[1]["caso_id"], again[1]["duplicado"]),
                         (200, case.id, True))
        self.assertEqual(self.api.conversation_handoff(conversation.id, {"tipo": "otro"})[0], 400)
        case.with_user(self.cobrador_n).action_take()
        self.assertEqual((case.state, case.assigned_to, conversation.attended_by),
                         ("atencion", self.cobrador_n, self.cobrador_n))
        case.with_user(self.cobrador_n).action_resolve()
        self.assertEqual((case.state, conversation.state), ("resuelto", "bot"))

    def test_person_reply(self):
        conversation = self._incoming("Hola")
        with self.assertRaises(AccessError):
            conversation.with_user(self.tecnico_n)._reply_as_person("x")
        with self.assertRaises(AccessError):
            conversation.with_user(self.cobrador_s)._reply_as_person("x")
        message = conversation.with_user(self.cobrador_n)._reply_as_person("Ya lo reviso")
        self.assertEqual((message.origin, conversation.state, conversation.attended_by),
                         ("persona", "humano", self.cobrador_n))
        conversation.sudo().last_incoming_at = fields.Datetime.now() - timedelta(hours=25)
        with self.assertRaises(UserError) as caught:
            conversation.with_user(self.cobrador_n)._reply_as_person("tarde")
        self.assertIn("plantilla", str(caught.exception))
        conversation.with_user(self.cobrador_n).action_return_to_bot()
        self.assertEqual(conversation.state, "bot")
        # Dos respuestas seguidas, aunque caigan en el mismo segundo, son dos mensajes.
        conversation.sudo().last_incoming_at = fields.Datetime.now()
        first = conversation.with_user(self.cobrador_n)._reply_as_person("Uno")
        second = conversation.with_user(self.cobrador_n)._reply_as_person("Dos")
        self.assertNotEqual(first, second)

    def test_simulator_never_reaches_meta_nor_opts_out(self):
        conversation = self.Conversation.with_user(self.cobrador_n)._simulate_incoming(
            "71006044", "BAJA")
        self.assertEqual((conversation.channel, conversation.partner_id),
                         ("simulador", self.cliente))
        self.assertFalse(self.env["mirabilenet.whatsapp.optout"].search([]))
        self.assertEqual(self._deliver()[0]["payload"]["canal"], "simulador")
        conversation.sudo()._enqueue_outgoing("texto", {"texto": "respuesta"}, "sim:1")
        self.env["mirabilenet.conversation.message"]._cron_dispatch()
        self.assertFalse(FakeMetaGateway.sent)
        with self.assertRaises(AccessError):
            self.Conversation.with_user(self.tecnico_n)._simulate_incoming("71006044", "x")
        with self.assertRaises(AccessError):
            self.Conversation.with_user(self.cobrador_s)._simulate_incoming("71006044", "x")

    def test_conversations_are_isolated_and_immutable(self):
        north = self._incoming("Hola")
        south = self._incoming("Hola", origin="59172000002", wamid="w-s")
        self.assertEqual(south.partner_id, self.cliente_s)
        found = self.Conversation.with_user(self.cobrador_n).search([])
        self.assertIn(north, found)
        self.assertNotIn(south, found)
        with self.assertRaises(AccessError):
            south.with_user(self.cobrador_n).read(["contact"])
        with self.assertRaises(AccessError):
            self.Conversation.with_user(self.pasante).search([])
        with self.assertRaises(UserError):
            north.with_user(self.cobrador_n).write({"state": "cerrada"})
        with self.assertRaises(UserError):
            north.message_ids.with_user(self.cobrador_n).write({"text": "otra cosa"})
        self.assertTrue(north.pending_review)
        north.with_user(self.cobrador_n).action_mark_reviewed()
        self.assertFalse(north.pending_review)
        self.assertNotIn(north, self.Conversation.search([("pending_review", "=", True)]))

    def test_conversation_message_status_from_meta(self):
        conversation = self._incoming("Hola")
        message, _c = conversation._enqueue_outgoing("texto", {"texto": "r"}, "k:1")
        message._dispatch()
        self.env["mirabilenet.whatsapp.message"]._process_webhook({"entry": [{"changes": [{
            "field": "messages", "value": {"statuses": [
                {"id": message.external_id, "status": "read"}]}}]}]})
        self.assertEqual(message.state, "leido")


@tagged("mirabilenet", "post_install", "-at_install")
class TestN8nTools(ConversationCommon):

    def setUp(self):
        super().setUp()
        self.settings.daily_limit = 20
        self.conversation = self._incoming("Hola")
        self.prospect = self._incoming("Info", origin="59179998888", wamid="w-p")

    def test_customer_tools_reject_prospects_and_unknown(self):
        for method in ("conversation_charges", "conversation_proofs", "conversation_service",
                       "conversation_plans", "conversation_retention_offers"):
            self.assertEqual(getattr(self.api, method)(self.prospect.id), (409, {
                "codigo": "no_es_cliente",
                "detail": "El contacto no es un cliente registrado."}), method)
            self.assertEqual(getattr(self.api, method)(999999),
                             (404, {"detail": "Conversacion inexistente."}), method)
        self.assertEqual(self.api.conversation_sales(self.conversation.id)[1]["codigo"],
                         "es_cliente")
        self.assertEqual(self.api.conversation_lead(self.conversation.id, {})[1]["codigo"],
                         "es_cliente")

    def test_conversation_state(self):
        status, body = self.api.conversation(self.conversation.id)
        self.assertEqual(status, 200)
        self.assertEqual(sorted(body), ["canal", "es_cliente", "estado", "id",
                                        "ventana_abierta", "ventana_hasta"])
        self.assertEqual((body["canal"], body["estado"], body["es_cliente"],
                          body["ventana_abierta"]), ("whatsapp", "bot", True, True))

    def test_charges_tool(self):
        charge = self._charge(month=10)
        status, body = self.api.conversation_charges(self.conversation.id)
        self.assertEqual(status, 200)
        self.assertEqual(body, {"avisos": [{
            "id": charge.id, "numero": charge.name, "concepto": "Hogar 20 - período 10/2026",
            "saldo": "300.00", "moneda": "BOB", "fecha_vencimiento": "2026-10-25",
            "vencido": True}]})

    def test_service_and_plans_tools(self):
        service = self._service()
        service._mirabilenet_ensure_contract(TODAY)
        service.contract_id.code = "CT-1"
        self.plan.mirabilenet_publish_web = True
        hidden = self.env["product.template"].create({
            "name": "Sin publicar", "type": "service", "mirabilenet_is_plan": True,
            "mirabilenet_plan_code": "T-OCULTO", "list_price": 50,
            "mirabilenet_down_mbps": 5, "mirabilenet_up_mbps": 5})
        body = self.api.conversation_service(self.conversation.id)[1]
        self.assertEqual(body, {
            "titular": "Juan  Pérez",
            "servicios": [{"plan": "Hogar 20", "bajada_mbps": 20, "subida_mbps": 10,
                           "precio_mensual": "300.00", "moneda": "BOB", "estado": "Activo"}],
            "contratos": [{"numero": "CT-1", "estado": "Vigente", "desde": "20/11/2026"}]})
        plans = self.api.conversation_plans(self.conversation.id)[1]
        self.assertEqual(plans["region_del_cliente"], "Norte")
        self.assertEqual(plans["tu_plan"][0]["nombre"], "Hogar 20")
        self.assertEqual(plans["planes_disponibles"], [{
            "nombre": "Hogar 20", "bajada_mbps": 20, "subida_mbps": 10,
            "precio_mensual": "300.00", "moneda": "BOB", "incluye_tv": False,
            "region": "Todas las regiones", "es_tu_plan": True}])
        self.assertNotIn(hidden.name, json.dumps(plans), "solo planes publicados")
        self.assertTrue(service)

    def test_history_and_style(self):
        self.conversation._enqueue_outgoing("texto", {"texto": "Hola, Juan"}, "k:1")
        status, body = self.api.conversation_history(self.conversation.id, {"limite": "5"})
        self.assertEqual(status, 200)
        self.assertEqual(body["mensajes"], [
            {"de": "cliente", "tipo": "texto", "texto": "Hola"},
            {"de": "bot", "tipo": "texto", "texto": "Hola, Juan"}])
        self.assertIn("resolutivo", body["estilo"])
        self.assertIn("vendedor", self.api.conversation_history(self.prospect.id, {})[1]["estilo"])

    def test_organization_is_public_information_only(self):
        self.env["mirabilenet.zone"].create(
            {"region_id": self.norte.id, "code": "T-Z1", "name": "Vinto", "sector": "Centro"})
        self.env["mirabilenet.bot.settings"]._load().sudo().about_us = "Somos de Oruro."
        body = self.api.conversation_organization(self.prospect.id)[1]
        self.assertEqual(sorted(body), ["empresa", "horario_de_atencion", "quienes_somos",
                                        "regiones"])
        self.assertEqual(body["quienes_somos"], "Somos de Oruro.")
        north = [r for r in body["regiones"] if r["region"] == "Norte"][0]
        self.assertEqual(north["sucursales"], [{"nombre": "Central Norte", "direccion": "",
                                                "telefono": "2-5550000"}])
        self.assertEqual(north["zonas"], [{"zona": "Vinto", "sector": "Centro"}])
        text = json.dumps(body)
        for internal in ("dia_emision", "wg_region", "objetivo", "10.250"):
            self.assertNotIn(internal, text)

    def test_sales_and_lead(self):
        self.plan.mirabilenet_publish_web = True
        self.env["mirabilenet.zone"].create(
            {"region_id": self.sur.id, "code": "T-Z2", "name": "Huanuni"})
        body = self.api.conversation_sales(self.prospect.id)[1]
        self.assertEqual(body["region_del_numero"], "Norte")
        self.assertEqual(body["planes"], [{
            "nombre": "Hogar 20", "region": "Todas las regiones", "bajada_mbps": 20,
            "subida_mbps": 10, "precio_mensual": "300.00", "moneda": "BOB",
            "incluye_tv": False}])
        self.assertIn({"region": "Sur", "zona": "Huanuni", "sector": "",
                       "estado": "Cobertura disponible", "detalle": ""}, body["cobertura"])
        self.assertEqual(self.api.conversation_lead(self.prospect.id, {"nombre": "A"}),
                         (400, {"codigo": "falta_nombre",
                                "detail": "Hace falta el nombre del interesado."}))
        status, lead = self.api.conversation_lead(self.prospect.id, {
            "nombre": "María Flores", "localidad": "Huanuni", "plan_interes": "Hogar 20",
            "mensaje": "Quiero contratar"})
        self.assertEqual((status, lead["duplicado"], lead["region"]), (201, False, "Norte"))
        record = self.env["crm.lead"].browse(lead["consulta_id"])
        self.assertEqual((record.contact_name, record.phone, record.city,
                          record.mirabilenet_plan_interest),
                         ("María Flores", "59179998888", "Huanuni", "Hogar 20"))
        self.assertFalse(self.env["res.partner"].search([("name", "=", "María Flores")]),
                         "no crea un cliente")
        again = self.api.conversation_lead(self.prospect.id, {"nombre": "María Flores"})
        self.assertEqual(again, (200, {"consulta_id": record.id, "duplicado": True}))

    def test_retention_offers(self):
        Promo = self.env["mirabilenet.retention.promo"]
        Promo.create({"name": "Descuento", "offer": "20 % por 3 meses", "sequence": 1,
                      "date_to": TODAY + timedelta(days=10)})
        Promo.create({"name": "Vencida", "offer": "x", "date_to": TODAY - timedelta(days=1)})
        Promo.create({"name": "Del sur", "offer": "y", "region_id": self.sur.id})
        Promo.create({"name": "Apagada", "offer": "z", "active": False})
        body = self.api.conversation_retention_offers(self.conversation.id)[1]
        self.assertEqual(body, {"promociones": [{
            "nombre": "Descuento", "oferta": "20 % por 3 meses", "condiciones": "",
            "vigente_hasta": (TODAY + timedelta(days=10)).strftime("%d/%m/%Y")}]})
        with self.assertRaises(AccessError):
            Promo.with_user(self.admin_n).create({"name": "Global", "offer": "g"})
        Promo.with_user(self.admin_n).create(
            {"name": "Norte", "offer": "n", "region_id": self.norte.id})

    def test_qr_tool(self):
        self.assertEqual(self.api.conversation_qr(self.conversation.id, {})[1]["codigo"],
                         "sin_qr")
        self.assertTrue(self.env["mirabilenet.integration.alert"].search(
            [("key", "=", "qr-faltante:%d" % self.norte.id)]))
        self.env["mirabilenet.payment.qr"].create({"region_id": self.norte.id, "image": PNG})
        charge = self._charge(month=10)
        status, body = self.api.conversation_qr(self.conversation.id, {"mensaje_id": 5})
        self.assertEqual((status, body["enviado"], body["duplicado"], body["region"]),
                         (201, True, False, "Norte"))
        self.assertEqual(body["avisos"], [{"numero": charge.name, "saldo": "300.00",
                                           "moneda": "BOB", "fecha_vencimiento": "25/10/2026"}])
        self.assertEqual(self.api.conversation_qr(self.conversation.id,
                                                  {"mensaje_id": 5})[1]["duplicado"], True)
        message = self.conversation.message_ids.filtered(lambda m: m.kind == "imagen")
        self.assertIn(charge.name, message.text)
        message._dispatch()
        kinds = [s["kind"] for s in FakeMetaGateway.sent]
        self.assertEqual(kinds, ["media", "session"])
        self.assertEqual(message.state, "enviado")
        self.assertFalse(message.file, "el archivo no se conserva después de enviarlo")
        self.assertFalse(self.env["account.payment"].search([("partner_id", "=", self.cliente.id)]), "el QR no registra pagos")

    def test_collection_endpoints(self):
        due_soon = self._charge(month=11, due=TODAY + timedelta(days=3))
        overdue = self._charge(month=10)
        status, body = self.api.charges({"dias": "3"})
        self.assertEqual((status, body["count"]), (200, 1))
        item = body["results"][0]
        self.assertEqual((item["id"], item["numero"], item["saldo"], item["estado"],
                          item["cliente"]["nombre"], item["region"]["codigo"], item["qr_url"]),
                         (due_soon.id, due_soon.name, "300.00", "emitido", "Juan  Pérez",
                          "T-N", None))
        self.assertEqual(self.api.charges({"vencidos": "true"})[1]["results"][0]["id"],
                         overdue.id)
        self.assertEqual(self.api.charges({"dias": "x"})[0], 400)
        self.assertEqual(self.api.charges({"dias": "400"})[0], 400)
        customer = self.api.customer({"telefono": "+591 71006044"})[1]
        self.assertEqual(customer["cliente"], {"nombre": "Juan  Pérez",
                                               "codigo": self.cliente.mirabilenet_code})
        self.assertEqual(len(customer["avisos"]), 2)
        self.assertEqual(self.api.customer({"telefono": "70000000"})[0], 404)

        self.env["mirabilenet.whatsapp.message"].search([]).sudo().unlink()
        status, body = self.api.reminders({"aviso_id": due_soon.id})
        self.assertEqual((status, body["duplicado"]), (201, False))
        self.assertEqual(self.api.reminders({"aviso_id": due_soon.id}), (200, {
            "id": body["id"], "estado": "pendiente", "duplicado": True}))
        self.assertEqual(self.api.reminders({"aviso_id": overdue.id})[0], 409)
        self.assertEqual(self.api.reminders({"aviso_id": 999999})[0], 404)
        self.assertEqual(self.api.reminders({"aviso_id": due_soon.id, "evento": "x"})[0], 400)
        self.assertEqual(self.api.reminders(
            {"aviso_id": due_soon.id, "evento": "aviso_vencido"})[0], 409)
        self.assertEqual(self.api.reminders(
            {"aviso_id": overdue.id, "evento": "recordatorio_mora", "clave_dia": "hoy"})[0], 400)
        self.assertEqual(self.api.opt_outs({"telefono": "71006044"}),
                         (200, {"baja": True, "duplicado": False}))
        self.assertEqual(self.api.opt_outs({"telefono": "71006044"})[1]["duplicado"], True)
        self.assertEqual(self.api.charges({"dias": "3"})[1]["count"], 0, "ya se dio de baja")

    def test_cases_and_alerts_and_quota(self):
        status, body = self.api.cases({"telefono": "71006044", "mensaje_id": "m1",
                                       "tipo": "baja_servicio", "motivo": "Me mudo"})
        self.assertEqual((status, body["estado"], body["duplicado"]), (201, "nuevo", False))
        self.assertEqual(self.api.cases({"telefono": "71006044", "mensaje_id": "m1"})[0], 200)
        self.assertEqual(self.api.cases({"telefono": "71006044"})[0], 400)
        self.assertEqual(self.api.cases({"telefono": "70000000", "mensaje_id": "m"})[0], 404)

        first = self.api.alerts({"workflow": "MIRABILENET · 15", "nodo": "Agente",
                                 "mensaje": "Falló", "ejecucion_id": "81"})
        self.assertEqual((first[0], first[1]["repeticiones"]), (201, 1))
        again = self.api.alerts({"workflow": "MIRABILENET · 15", "nodo": "Agente",
                                 "mensaje": "Falló"})
        self.assertEqual((again[0], again[1]["id"], again[1]["repeticiones"]),
                         (200, first[1]["id"], 2))
        self.assertEqual(self.api.alerts({"workflow": "x"})[0], 400)

        self.assertEqual(self.api.ia_exhausted({"modelo": "models/otro"})[0], 400)
        status, body = self.api.ia_exhausted(
            {"modelo": "models/gemini-flash-lite-latest", "detalle": "too many requests"})
        self.assertEqual((status, body), (201, {
            "agotado": "models/gemini-flash-lite-latest",
            "siguiente": "models/gemini-flash-latest"}))
        self.assertEqual(self.api.ia_exhausted(
            {"modelo": "models/gemini-flash-lite-latest"})[0], 200)
        Bot = self.env["mirabilenet.bot.settings"]
        self.assertEqual(Bot._for_event()["modelo"], "models/gemini-flash-latest")
        self.api.ia_exhausted({"modelo": "models/gemini-flash-latest"})
        self.assertEqual(Bot._for_event(), {"soporte": True, "ventas": True, "modelo": "",
                                            "disponible": False})
        tomorrow = fields.Datetime.now() + timedelta(days=2)
        self.assertTrue(Bot._for_event(now=tomorrow)["disponible"], "el cupo se repone")

    def test_bot_settings_rules(self):
        settings = self.env["mirabilenet.bot.settings"]._load()
        with self.assertRaises(AccessError):
            settings.with_user(self.admin_n).write({"support_on": False})
        with self.assertRaises(AccessError):
            settings.with_user(self.auditor).write({"support_on": False})
        settings.with_user(self.gerencia).write({"support_on": False, "daily_limit": 1})
        self.assertFalse(self.env["mirabilenet.bot.settings"]._for_event()["soporte"])
        with self.assertRaises(ValidationError):
            settings.sudo().model = "gemini"
        with self.assertRaises(ValidationError):
            settings.sudo().backup_model = settings.model
        # Con tope propio de 1, tras una respuesta el principal queda al límite.
        self.api.messages({"conversacion_id": self.conversation.id, "tipo": "texto",
                           "clave": "c:1", "contenido": {"texto": "r",
                                                         "modelo": settings.model}})
        self.env.flush_all()
        self.assertEqual(settings._model_to_use(), settings.backup_model)
        with self.assertRaises(UserError):
            self.env["mirabilenet.bot.settings"].sudo().create({})


@tagged("mirabilenet", "post_install", "-at_install")
class TestProofs(ConversationCommon):

    def setUp(self):
        super().setUp()
        self.settings.daily_limit = 20
        FakeMetaGateway.media["MEDIA1"] = (JPG, "image/jpeg")
        self.Proof = self.env["mirabilenet.whatsapp.proof"]

    def _send_file(self, wamid="wamid.P1", media="MEDIA1"):
        incoming = {"from": "59171006044", "id": wamid, "type": "image",
                    "image": {"id": media, "mime_type": "image/jpeg"},
                    "timestamp": str(int(fields.Datetime.now().timestamp()))}
        self.Conversation._process_meta_incoming(incoming, "PN-N")
        return self.Proof.search([("whatsapp_message_id", "=", wamid)])

    def test_single_pending_charge_is_associated(self):
        charge = self._charge(month=10)
        proof = self._send_file()
        self.assertEqual((proof.state, proof.charge_id, proof.mime_type, proof.simulated),
                         ("revision", charge, "image/jpeg", False))
        self.assertEqual(charge.amount_residual, 300, "recibir el archivo no registra el pago")
        self.assertFalse(self.env["account.payment"].search([("partner_id", "=", self.cliente.id)]))
        event = self._deliver()[0]["payload"]
        self.assertEqual(event["manejado_por_sistema"], "comprobante")
        self.assertEqual(event["comprobante"], {
            "resultado": "guardado", "comprobante_id": proof.id,
            "aviso_numero": charge.name, "avisos_pendientes": 1})
        self._send_file()
        self.assertEqual(len(self.Proof.search([])), 1, "Meta lo repitió: no se duplica")

    def test_several_charges_wait_for_the_customer_choice(self):
        first = self._charge(month=10)
        second = self._charge(month=11)
        proof = self._send_file()
        self.assertFalse(proof.charge_id)
        event = self._deliver()[0]["payload"]["comprobante"]
        self.assertEqual((event["aviso_numero"], event["avisos_pendientes"]), (None, 2))
        conversation = self.Conversation.search([], limit=1)
        status, body = self.api.proof_charge(conversation.id, proof.id, {"aviso_id": second.id})
        self.assertEqual((status, body), (200, {
            "comprobante_id": proof.id, "aviso_numero": second.name, "saldo": "300.00",
            "moneda": "BOB"}))
        other = self._charge(partner=self.cliente_s)
        self.assertEqual(self.api.proof_charge(conversation.id, proof.id,
                                               {"aviso_id": other.id})[1]["codigo"],
                         "no_asociable")
        self.assertEqual(self.api.proof_charge(conversation.id, 999999, {})[0], 404)
        self.assertEqual(proof.charge_id, second)
        self.assertTrue(first)

    def test_bad_or_missing_files(self):
        self._charge(month=10)
        FakeMetaGateway.media["MALO"] = (b"<html>no es un comprobante</html>", "text/html")
        self._send_file(wamid="w-malo", media="MALO")
        self._send_file(wamid="w-perdido", media="NO-EXISTE")
        self.assertFalse(self.Proof.search([]))
        results = [e["payload"]["comprobante"]["resultado"] for e in self._deliver()]
        self.assertEqual(results, ["formato_no_valido", "no_recibido"])

    def test_verification_registers_the_payment(self):
        service = self._service()
        service.sudo().state = "suspendido"
        charge = self._invoice(service, 10)
        proof = self._send_file()
        conversation = self.Conversation.search([], limit=1)
        with self.assertRaises(AccessError):
            proof.with_user(self.tecnico_n).action_verify()
        with self.assertRaises(AccessError):
            proof.with_user(self.cobrador_s).action_verify()
        proof.with_user(self.cajero_n).action_verify()
        self.assertEqual((proof.state, proof.reviewed_by), ("verificado", self.cajero_n))
        payment = proof.payment_id
        self.assertEqual((payment.amount, payment.partner_id, payment.mirabilenet_region_id,
                          payment.create_uid),
                         (300, self.cliente, self.norte, self.cajero_n))
        self.assertIn(payment.state, ("in_process", "paid"))
        self.assertEqual((charge._mirabilenet_charge_state(), charge.amount_residual),
                         ("pagado", 0))
        self.assertEqual(service.transition_ids.action, "activar",
                         "el pago aprobado es lo que pide reactivar")
        notice = conversation.message_ids.filtered(lambda m: m.origin == "persona")
        self.assertIn("Pago verificado con éxito", notice.text)
        self.assertTrue(proof.customer_notified)
        with self.assertRaises(UserError):
            proof.with_user(self.cajero_n).action_verify()
        self.assertEqual(len(self.env["account.payment"].search([("partner_id", "=", self.cliente.id)])), 1)

    def test_verification_needs_charge_and_active_register(self):
        self._charge(month=10)
        self._charge(month=11)
        proof = self._send_file()
        with self.assertRaises(UserError):
            proof.with_user(self.cajero_n).action_verify()  # sin aviso asociado
        proof.with_user(self.cajero_n).write({"charge_id": self._charge(month=12).id})
        self.assertEqual(proof.state, "revision")
        proof.with_user(self.cajero_n).action_verify()
        self.assertEqual(proof.state, "verificado")

    def test_notice_falls_back_to_a_template_outside_the_window(self):
        self.env["mirabilenet.whatsapp.template"].create(
            {"event": "comprobante_verificado", "meta_name": "pago_verificado",
             "variables": "cliente, numero_aviso"})
        charge = self._charge(month=10)
        proof = self._send_file()
        self.Conversation.search([], limit=1).sudo().last_incoming_at = \
            fields.Datetime.now() - timedelta(hours=30)
        proof.with_user(self.cajero_n).action_verify()
        message = self.env["mirabilenet.whatsapp.message"].search(
            [("event", "=", "comprobante_verificado")])
        self.assertEqual(message.parameters, ["Juan Pérez", charge.name])
        self.assertTrue(proof.customer_notified)

    def test_reject_and_simulated(self):
        self._charge(month=10)
        proof = self._send_file()
        with self.assertRaises(UserError):
            proof.with_user(self.cajero_n).action_reject("")
        proof.with_user(self.cajero_n).action_reject("No se lee el monto")
        self.assertEqual((proof.state, proof.reject_reason),
                         ("rechazado", "No se lee el monto"))
        self.assertFalse(self.env["account.payment"].search([("partner_id", "=", self.cliente.id)]))
        _result, simulated = self.Proof._store(self.cliente, PDF, "sim-1", simulated=True)
        with self.assertRaises(UserError):
            simulated.with_user(self.cajero_n).action_verify()
        simulated.with_user(self.cajero_n).action_reject("Prueba")

    def test_proofs_are_protected_and_isolated(self):
        self._charge(month=10)
        proof = self._send_file()
        with self.assertRaises(UserError):
            proof.with_user(self.cajero_n).write({"state": "verificado"})
        with self.assertRaises(UserError):
            proof.sudo().unlink()
        with self.assertRaises(UserError):
            self.Proof.with_user(self.cajero_n).create(
                {"partner_id": self.cliente.id, "whatsapp_message_id": "x"})
        self.assertFalse(self.Proof.with_user(self.cobrador_s).search([]))
        conversation = self.Conversation.search([], limit=1)
        body = self.api.conversation_proofs(conversation.id)[1]
        self.assertEqual(body["comprobantes"][0]["estado"], "En verificacion")
        self.assertEqual(sorted(body["comprobantes"][0]),
                         ["aviso_numero", "estado", "motivo_rechazo", "recibido"])

    def test_proof_upload_endpoint(self):
        charge = self._charge(month=10)
        data = {"telefono": "71006044", "aviso_id": str(charge.id), "mensaje_id": "up-1"}
        self.assertEqual(self.api.proof_upload(data, PDF, "application/pdf")[0], 201)
        self.assertEqual(self.api.proof_upload(data, PDF, "application/pdf")[1]["duplicado"],
                         True)
        self.assertEqual(self.api.proof_upload(data, None, "")[0], 400)
        self.assertEqual(self.api.proof_upload(data, PDF, "image/png")[0], 400)
        self.assertEqual(self.api.proof_upload(dict(data, aviso_id="0"), PDF,
                                               "application/pdf")[0], 400)
        self.assertEqual(self.api.proof_upload(dict(data, telefono="70000000"), PDF,
                                               "application/pdf")[0], 404)


@tagged("mirabilenet", "post_install", "-at_install")
class TestN8nHttp(HttpCase):
    """La puerta HTTP: sin el token de n8n no se entra."""

    def test_token_is_required(self):
        url = "/api/v1/messaging/n8n/charges"
        with patch.dict(os.environ, ENV):
            self.assertEqual(self.url_open(url).status_code, 403)
            self.assertEqual(self.url_open(
                url, headers={"Authorization": "Bearer otro"}).status_code, 403)
            ok = self.url_open(url, headers={"Authorization": "Bearer token-de-n8n"})
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(sorted(ok.json()), ["count", "results"])
            missing = self.url_open(
                "/api/v1/messaging/n8n/conversations/999999",
                headers={"Authorization": "Bearer token-de-n8n"})
            self.assertEqual((missing.status_code, missing.json()),
                             (404, {"detail": "Conversacion inexistente."}))
            bad = self.url_open("/api/v1/messaging/n8n/messages", data="no es json",
                                headers={"Authorization": "Bearer token-de-n8n"})
            self.assertEqual(bad.status_code, 400)
        with patch.dict(os.environ, {n8n.TOKEN_ENV: ""}):
            self.assertEqual(self.url_open(
                url, headers={"Authorization": "Bearer "}).status_code, 403)

    def test_meta_webhook_signature(self):
        settings = self.env["mirabilenet.whatsapp.settings"]._load()
        with patch.dict(os.environ, {"MIRABILENET_MASTER_KEY": "clave-de-prueba"}):
            settings.write({"app_secret": "secreto-app", "webhook_verify_token": "verificame"})
            path = "/api/v1/messaging/whatsapp/webhook"
            challenge = self.url_open(
                path + "?hub.mode=subscribe&hub.verify_token=verificame&hub.challenge=4242")
            self.assertEqual((challenge.status_code, challenge.text), (200, "4242"))
            self.assertEqual(self.url_open(
                path + "?hub.mode=subscribe&hub.verify_token=otro&hub.challenge=1"
            ).status_code, 403)
            body = json.dumps({"entry": []})
            signature = "sha256=" + hmac.new(b"secreto-app", body.encode(),
                                              hashlib.sha256).hexdigest()
            headers = {"Content-Type": "application/json"}
            self.assertEqual(self.url_open(path, data=body, headers=headers).status_code, 403)
            self.assertEqual(self.url_open(path, data=body, headers=dict(
                headers, **{"X-Hub-Signature-256": "sha256=" + "0" * 64})).status_code, 403)
            ok = self.url_open(path, data=body, headers=dict(
                headers, **{"X-Hub-Signature-256": signature}))
            self.assertEqual((ok.status_code, ok.json()), (200, {"ok": True}))
