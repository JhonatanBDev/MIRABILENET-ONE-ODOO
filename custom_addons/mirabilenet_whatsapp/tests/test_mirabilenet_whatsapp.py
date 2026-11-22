import base64
import os
from datetime import date, datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.mirabilenet_isp.isp import vault

from ..whatsapp import phones
from ..whatsapp.gateway import FakeMetaGateway

TODAY = date(2026, 11, 20)
PNG = base64.b64encode(
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0"
    b"\xa5\x00\x00\x00\x00IEND\xaeB`\x82")


@tagged("mirabilenet", "post_install", "-at_install")
class TestPhones(TransactionCase):

    def test_normalize(self):
        for raw in ("71006044", "+591 71006044", "00591-71006044", "(591) 7100 6044"):
            self.assertEqual(phones.normalize_number(raw), "59171006044", raw)
        for bad in ("", None, "abc", "22445566", "7100", "5917100"):
            with self.assertRaises(phones.NotSendable, msg=repr(bad)):
                phones.normalize_number(bad)

    def test_opt_out_words(self):
        for text in ("BAJA", " stop ", "Salir.", "No más mensajes", "Cancelar mensajes"):
            self.assertTrue(phones.is_opt_out(text), text)
        for text in ("Quiero dar de baja mi servicio", "hola", "cancelar", ""):
            self.assertFalse(phones.is_opt_out(text), text)

    def test_clean_parameter(self):
        self.assertEqual(phones.clean_parameter("  Juan \n Pérez  "), "Juan Pérez")
        self.assertEqual(phones.clean_parameter(""), "-")
        self.assertEqual(phones.clean_parameter(None), "-")


class WhatsappCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.startClassPatcher(patch.dict(os.environ, {vault.ENV_VAR: "clave-de-prueba"}))
        cls.startClassPatcher(patch.object(
            type(cls.env["account.move"]), "_mirabilenet_today", lambda self: TODAY))
        cls.env.ref("base.BOB").active = True
        # Las facturas necesitan un plan de cuentas en la empresa de las pruebas.
        company = cls.env.company
        if not cls.env["account.journal"].search_count(
                [("type", "=", "sale"), ("company_id", "=", company.id)]):
            cls.env["account.chart.template"].try_loading(
                "generic_coa", company=company, install_demo=False)
        cls.env["ir.config_parameter"].set_param("mirabilenet.meta_gateway", "fake")
        cls.env["ir.config_parameter"].set_param(
            "mirabilenet.messaging_public_url", "https://mensajes.example")
        FakeMetaGateway.reset()

        Region = cls.env["mirabilenet.region"]
        cls.norte = Region.create({"code": "T-N", "name": "Norte", "wg_region_id": 1,
                                   "dia_vencimiento": 25})
        cls.sur = Region.create({"code": "T-S", "name": "Sur", "wg_region_id": 2})
        Branch = cls.env["mirabilenet.branch"]
        cls.branch_n = Branch.create({"region_id": cls.norte.id, "code": "TN1",
                                      "name": "Central Norte", "phone": "2-5550000"})
        cls.branch_s = Branch.create({"region_id": cls.sur.id, "code": "TS1", "name": "Sur"})

        cls.gerencia = cls._user("t_gerencia", "gerencia")
        cls.auditor = cls._user("t_auditor", "auditor")
        cls.finanzas_n = cls._user("t_finanzas_n", "finanzas", cls.norte)
        cls.admin_n = cls._user("t_admin_n", "admin_regional", cls.norte)
        cls.cobrador_n = cls._user("t_cobrador_n", "cobrador", cls.norte)
        cls.cobrador_s = cls._user("t_cobrador_s", "cobrador", cls.sur)
        cls.tecnico_n = cls._user("t_tecnico_n", "tecnico", cls.norte)
        cls.pasante = cls._user("t_pasante", "pasante", cls.norte)

        cls.settings = cls.env["mirabilenet.whatsapp.settings"]._load()
        cls.settings.write({"active_messaging": True, "test_mode": False, "waba_id": "WABA1",
                            "access_token": "token-meta", "app_secret": "secreto-app",
                            "webhook_verify_token": "verificame", "hour_start": 0,
                            "hour_end": 24})
        Number = cls.env["mirabilenet.whatsapp.number"]
        cls.number_n = Number.create({"branch_id": cls.branch_n.id, "phone_number_id": "PN-N",
                                      "display_number": "+59170000001"})
        cls.number_s = Number.create({"branch_id": cls.branch_s.id, "phone_number_id": "PN-S",
                                      "display_number": "+59170000002"})
        Template = cls.env["mirabilenet.whatsapp.template"]
        cls.tpl_emitido = Template.create({
            "event": "aviso_emitido", "meta_name": "aviso_cobro",
            "variables": "cliente, numero_aviso, saldo, fecha_vencimiento, sucursal"})
        for event in ("recordatorio_pago", "aviso_vencido", "recordatorio_mora"):
            Template.create({"event": event, "meta_name": event,
                             "variables": "cliente, saldo"})

        Partner = cls.env["res.partner"]
        cls.cliente = Partner.create({
            "name": "Juan  Pérez", "mirabilenet_is_customer": True,
            "mirabilenet_region_id": cls.norte.id, "mirabilenet_whatsapp": "+591 7100-6044",
            "mirabilenet_branch_id": cls.branch_n.id})
        cls.cliente_s = Partner.create({
            "name": "Cliente Sur", "mirabilenet_is_customer": True,
            "mirabilenet_region_id": cls.sur.id, "phone": "72000002"})
        cls.plan = cls.env["product.template"].create({
            "name": "Hogar 20", "type": "service", "mirabilenet_is_plan": True,
            "mirabilenet_plan_code": "T-HOGAR-W", "list_price": 300,
            "mirabilenet_down_mbps": 20, "mirabilenet_up_mbps": 10})
        Consent = cls.env["mirabilenet.whatsapp.consent"]
        for partner in (cls.cliente, cls.cliente_s):
            Consent.create({"partner_id": partner.id, "origin": "contrato",
                            "detail": "Contrato de prueba"})

    @classmethod
    def _user(cls, login, role, region=None):
        user = new_test_user(cls.env, login, groups="base.group_user")
        user.write({"mirabilenet_role": role,
                    "mirabilenet_region_id": region.id if region else False})
        return user

    def setUp(self):
        super().setUp()
        FakeMetaGateway.reset()

    def _service(self, partner=None):
        service = self.env["mirabilenet.service"].create(
            {"partner_id": (partner or self.cliente).id, "plan_id": self.plan.id})
        service.state = "activo"
        return service

    def _invoice(self, service, month=11, due=None):
        """Una factura publicada del servicio, como la que emite su contrato."""
        move = self.env["account.move"].create({
            "move_type": "out_invoice", "partner_id": service.partner_id.id,
            "invoice_date": date(2026, month, 1),
            "invoice_date_due": due or date(2026, month, 25),
            "mirabilenet_service_id": service.id,
            "mirabilenet_region_id": service.region_id.id,
            "currency_id": service.region_id.currency_id.id,
            "invoice_line_ids": [(0, 0, {
                "product_id": self.plan.product_variant_id.id, "quantity": 1,
                "name": "Hogar 20 - período %02d/2026" % month, "price_unit": 300,
                "tax_ids": [(5, 0, 0)]})]})
        move.action_post()
        move._mirabilenet_notify("aviso_emitido")
        return move

    def _charge(self, partner=None, month=11, due=None):
        return self._invoice(self._service(partner), month, due)

    @property
    def Message(self):
        return self.env["mirabilenet.whatsapp.message"]

    def _messages(self, **domain):
        return self.Message.search([(k, "=", v) for k, v in domain.items()])


@tagged("mirabilenet", "post_install", "-at_install")
class TestEnqueue(WhatsappCommon):

    def test_charge_emission_enqueues_once(self):
        charge = self._charge()
        message = charge.whatsapp_message_ids
        self.assertEqual(len(message), 1)
        self.assertEqual((message.event, message.state, message.destination),
                         ("aviso_emitido", "pendiente", "59171006044"))
        self.assertEqual(message.unique_key, "aviso_emitido:%s" % charge.name)
        self.assertEqual(message.parameters,
                         ["Juan Pérez", charge.name, "300.00", "25/11/2026", "Central Norte"])
        self.assertEqual((message.number_id, message.region_id), (self.number_n, self.norte))
        # Volver a emitir o a notificar no escribe dos veces.
        charge._mirabilenet_notify("aviso_emitido")
        self.assertFalse(self.Message._enqueue("aviso_emitido", charge=charge))
        self.assertEqual(len(charge.whatsapp_message_ids), 1)

    def test_nothing_goes_out_when_switched_off(self):
        self.settings.active_messaging = False
        charge = self._charge()
        self.assertFalse(charge.whatsapp_message_ids)

    def test_consent_is_implied_by_default(self):
        """Al contratar se informa que se puede contactar al cliente: no hace falta un
        registro por cliente, salvo que la empresa decida exigirlo."""
        self.assertFalse(self.settings.require_consent)
        self.env["mirabilenet.whatsapp.consent"].search(
            [("partner_id", "=", self.cliente.id)]).sudo().unlink()
        self.assertTrue(self._charge(month=10).whatsapp_message_ids)
        self.settings.require_consent = True
        self.assertFalse(self._charge(month=11).whatsapp_message_ids)
        self.env["mirabilenet.whatsapp.consent"].create(
            {"partner_id": self.cliente.id, "origin": "contrato", "detail": "Contrato 123"})
        self.assertTrue(self._charge(month=12).whatsapp_message_ids)

    def test_opt_out_blocks_and_discards_pending(self):
        charge = self._charge()
        pending = charge.whatsapp_message_ids
        self.env["mirabilenet.whatsapp.optout"].with_user(self.cobrador_n).create(
            {"partner_id": self.cliente.id, "reason": "Lo pidió por teléfono"})
        self.assertEqual(pending.state, "descartado")
        self.assertFalse(self._charge(month=12).whatsapp_message_ids)

    def test_customer_without_mobile_does_not_break_the_cycle(self):
        self.cliente.write({"mirabilenet_whatsapp": False, "phone": "2-2445566"})
        charge = self._charge()
        self.assertTrue(charge.name, "el aviso se emite igual")
        self.assertFalse(charge.whatsapp_message_ids)

    def test_no_template_or_unhooked_event(self):
        self.tpl_emitido.active = False
        self.assertFalse(self._charge().whatsapp_message_ids)
        with self.assertRaises(phones.NotSendable):
            self.Message._enqueue("servicio_suspendido", partner=self.cliente)

    def test_daily_limit(self):
        first = self._charge(month=10)
        second = self._charge(month=11)
        third = self._charge(month=12)
        self.assertTrue(first.whatsapp_message_ids and second.whatsapp_message_ids)
        self.assertFalse(third.whatsapp_message_ids, "tope de 2 por cliente y día")

    def test_sender_choice(self):
        self.assertEqual(self._charge().whatsapp_message_ids.number_id, self.number_n)
        self.number_s.with_user(self.gerencia).write({"shared_global": True})
        message = self._charge(month=12).whatsapp_message_ids
        self.assertEqual(message.number_id, self.number_s, "el compartido tiene prioridad")
        # Compartir el remitente no comparte datos: región y sucursal son las del cliente.
        self.assertEqual(message.region_id, self.norte)
        self.assertEqual(message.parameters[-1], "Central Norte")

    def test_silence_when_a_person_is_attending(self):
        self.number_n.mode = "coexistencia"
        self.env["mirabilenet.whatsapp.agent.activity"]._record_echo(
            self.number_n, "59171006044", fields.Datetime.now() - timedelta(hours=2))
        self.assertFalse(self._charge().whatsapp_message_ids)
        self.number_n.mode = "api_pura"
        self.assertTrue(self._charge(month=12).whatsapp_message_ids)

    def test_qr_header(self):
        self.tpl_emitido.qr_header = True
        self.assertFalse(self._charge(month=10).whatsapp_message_ids, "sin QR vigente no sale")
        qr = self.env["mirabilenet.payment.qr"].with_user(self.finanzas_n).create(
            {"region_id": self.norte.id, "image": PNG})
        message = self._charge(month=11).whatsapp_message_ids
        self.assertEqual(message.header_image_url, qr.public_url)
        self.assertTrue(qr.public_url.startswith("https://mensajes.example/mirabilenet/qr/"))
        newer = self.env["mirabilenet.payment.qr"].create(
            {"region_id": self.norte.id, "image": PNG})
        self.assertFalse(qr.active, "el anterior queda archivado")
        self.assertEqual(self.env["mirabilenet.payment.qr"]._current(self.norte), newer)


@tagged("mirabilenet", "post_install", "-at_install")
class TestDispatch(WhatsappCommon):

    def test_dispatch_sends_the_template(self):
        message = self._charge().whatsapp_message_ids
        self.Message._cron_dispatch_pending()
        self.assertEqual((message.state, message.attempts), ("enviado", 1))
        self.assertTrue(message.wa_message_id.startswith("wamid.FAKE"))
        sent = FakeMetaGateway.sent[0]
        self.assertEqual((sent["phone_number_id"], sent["destino"], sent["plantilla"],
                          sent["token"]), ("PN-N", "59171006044", "aviso_cobro", "token-meta"))
        self.assertEqual(sent["parametros"], message.parameters)
        self.assertTrue(self.number_n.verified_at)
        self.Message._cron_dispatch_pending()
        self.assertEqual(len(FakeMetaGateway.sent), 1, "no se envía dos veces")

    def test_outside_the_window_messages_wait(self):
        self.settings.write({"hour_start": 8, "hour_end": 20})
        message = self._charge().whatsapp_message_ids
        Settings = type(self.settings)
        with patch.object(Settings, "_in_window", lambda s, moment=None: False):
            self.assertEqual(self.Message._cron_dispatch_pending(), 0)
        self.assertEqual(message.state, "pendiente", "espera en cola, no se pierde")
        with patch.object(Settings, "_in_window", lambda s, moment=None: True):
            self.Message._cron_dispatch_pending()
        self.assertEqual(message.state, "enviado")

    def test_window_hours(self):
        self.settings.write({"hour_start": 8, "hour_end": 20})
        # 12:00 UTC = 08:00 en Bolivia; 11:59 UTC = 07:59.
        self.assertTrue(self.settings._in_window(datetime(2026, 11, 20, 12, 0)))
        self.assertFalse(self.settings._in_window(datetime(2026, 11, 20, 11, 59)))
        self.assertFalse(self.settings._in_window(datetime(2026, 11, 21, 0, 30)))

    def test_test_mode_never_reaches_meta(self):
        self.settings.test_mode = True
        message = self._charge().whatsapp_message_ids
        message._dispatch()
        self.assertEqual((message.state, message.wa_message_id), ("enviado", "modo-prueba"))
        self.assertFalse(FakeMetaGateway.sent)

    def test_retryable_and_definitive_failures(self):
        message = self._charge().whatsapp_message_ids
        FakeMetaGateway.fail_next("Límite de mensajes", code="130429", retryable=True)
        message._dispatch()
        self.assertEqual((message.state, message.attempts, message.error_code),
                         ("pendiente", 1, "130429"))
        FakeMetaGateway.fail_next("Plantilla inexistente", code="132001")
        message._dispatch()
        self.assertEqual((message.state, message.attempts), ("fallido", 2))
        self.assertIn("Plantilla inexistente", message.error_detail)
        self.assertIn("Plantilla inexistente", self.number_n.last_error)

    def test_retries_are_capped(self):
        message = self._charge().whatsapp_message_ids
        for _i in range(3):
            FakeMetaGateway.fail_next("Temporal", code="131000", retryable=True)
            self.Message._cron_dispatch_pending()
        self.assertEqual((message.state, message.attempts), ("fallido", 3))

    def test_inactive_number_or_late_opt_out_discards(self):
        message = self._charge(month=10).whatsapp_message_ids
        self.number_n.active = False
        message._dispatch()
        self.assertEqual(message.state, "descartado")
        self.assertFalse(FakeMetaGateway.sent)

    def test_missing_master_key_does_not_crash(self):
        message = self._charge().whatsapp_message_ids
        with patch.dict(os.environ, clear=True):
            message._dispatch()
        self.assertEqual(message.state, "fallido")
        self.assertIn("clave maestra", message.error_detail)

    def test_log_is_immutable(self):
        message = self._charge().whatsapp_message_ids
        for user in (self.finanzas_n, self.gerencia):
            with self.assertRaises(UserError):
                message.with_user(user).write({"state": "leido"})
            with self.assertRaises(UserError):
                message.with_user(user).with_context(mirabilenet_billing=True).unlink()
        with self.assertRaises(UserError):
            self.Message.with_user(self.finanzas_n).create(
                {"partner_id": self.cliente.id, "region_id": self.norte.id,
                 "event": "aviso_emitido", "destination": "59170000000", "unique_key": "x"})


@tagged("mirabilenet", "post_install", "-at_install")
class TestCollectionCrons(WhatsappCommon):

    def setUp(self):
        super().setUp()
        self.settings.daily_limit = 10

    def test_reminder_days_before_due(self):
        due_in_3 = self._charge(month=11, due=TODAY + timedelta(days=3))
        self._charge(month=12, due=TODAY + timedelta(days=4))
        self.assertEqual(self.Message._cron_reminders(), 1)
        self.assertEqual(self.Message._cron_reminders(), 0, "uno por aviso")
        self.assertTrue(self._messages(charge_id=due_in_3.id, event="recordatorio_pago"))

    def test_overdue_notice(self):
        charge = self._charge(month=10)
        self.assertEqual(charge._mirabilenet_charge_state(), "vencido")
        self.assertEqual(self.Message._cron_overdue(), 1)
        self.assertEqual(len(self._messages(charge_id=charge.id, event="aviso_vencido")), 1)
        self.assertEqual(self.Message._cron_overdue(), 0, "ya se avisó al vencer")

    def test_mora_reminders_are_spaced_and_capped(self):
        charge = self._charge(month=10)
        self.assertEqual(self.Message._cron_overdue(), 1)
        self.assertEqual(self.Message._cron_mora_retries(), 0, "recién se avisó la mora")
        first = self._messages(charge_id=charge.id, event="aviso_vencido")
        self.cr.execute("UPDATE mirabilenet_whatsapp_message SET create_date = %s, "
                        "state = 'enviado' WHERE id = %s",
                        [fields.Datetime.now() - timedelta(days=8), first.id])
        first.invalidate_recordset()
        self.assertEqual(self.Message._cron_mora_retries(), 1)
        self.assertEqual(self.Message._cron_mora_retries(), 0, "el anterior sigue pendiente")
        self.settings.mora_max_reminders = 1
        self.cr.execute("UPDATE mirabilenet_whatsapp_message SET create_date = %s, "
                        "state = 'enviado' WHERE event = 'recordatorio_mora'",
                        [fields.Datetime.now() - timedelta(days=8)])
        self.Message.invalidate_model()
        self.assertEqual(self.Message._cron_mora_retries(), 0, "tope de recordatorios")

    def test_collection_can_be_delegated_to_n8n(self):
        self._charge(month=11, due=TODAY + timedelta(days=3))
        self.env["ir.config_parameter"].set_param("mirabilenet.n8n_controls_collection", "1")
        self.assertEqual(self.Message._cron_reminders(), 0)

    def test_paid_charges_get_no_reminders(self):
        charge = self._charge(month=11, due=TODAY + timedelta(days=3))
        charge._mirabilenet_register_payment()
        self.assertEqual(self.Message._cron_reminders(), 0)


@tagged("mirabilenet", "post_install", "-at_install")
class TestWebhook(WhatsappCommon):

    def _status(self, wa_id, status, **extra):
        return {"entry": [{"changes": [{"field": "messages", "value": {
            "statuses": [dict(id=wa_id, status=status, **extra)]}}]}]}

    def _incoming(self, text, origin="59171006044"):
        return {"entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "PN-N"},
            "messages": [{"from": origin, "id": "wamid.IN1", "type": "text",
                          "text": {"body": text}}]}}]}]}

    def test_delivery_states_never_go_back(self):
        message = self._charge().whatsapp_message_ids
        message._dispatch()
        wa_id = message.wa_message_id
        self.Message._process_webhook(self._status(wa_id, "read"))
        self.assertEqual(message.state, "leido")
        self.assertTrue(message.read_at)
        self.Message._process_webhook(self._status(wa_id, "delivered"))
        self.assertEqual(message.state, "leido", "un estado atrasado no retrocede")
        self.Message._process_webhook(self._status(
            wa_id, "failed", errors=[{"code": 131026, "title": "No disponible"}]))
        self.assertEqual((message.state, message.error_code, message.error_detail),
                         ("fallido", "131026", "No disponible"))
        self.assertEqual(self.Message._process_webhook(
            self._status("desconocido", "read"))["estados"], 0)

    def test_opt_out_word_from_the_customer(self):
        pending = self._charge().whatsapp_message_ids
        summary = self.Message._process_webhook(self._incoming("  BAJA "))
        self.assertEqual(summary["bajas"], 1)
        optout = self.env["mirabilenet.whatsapp.optout"].search(
            [("partner_id", "=", self.cliente.id)])
        self.assertEqual(optout.origin, "cliente")
        self.assertEqual(pending.state, "descartado")
        self.assertEqual(self.Message._process_webhook(self._incoming("STOP"))["bajas"], 1)
        self.assertEqual(len(self.env["mirabilenet.whatsapp.optout"].search(
            [("partner_id", "=", self.cliente.id)])), 1, "no se duplica")

    def test_other_messages_are_not_opt_outs(self):
        self.Message._process_webhook(self._incoming("Quiero dar de baja mi servicio"))
        self.Message._process_webhook(self._incoming("BAJA", origin="59179999999"))
        self.assertFalse(self.env["mirabilenet.whatsapp.optout"].search([]))

    def test_agent_echo_records_only_when(self):
        body = {"entry": [{"changes": [{"field": "smb_message_echoes", "value": {
            "metadata": {"phone_number_id": "PN-N"},
            "message_echoes": [{"to": "59171006044", "timestamp": "1795000000",
                                "text": {"body": "Hola, le escribo de la sucursal"}}]}}]}]}
        self.assertEqual(self.Message._process_webhook(body)["ecos"], 1)
        activity = self.env["mirabilenet.whatsapp.agent.activity"].search([])
        self.assertEqual((activity.contact, activity.partner_id, activity.number_id),
                         ("59171006044", self.cliente, self.number_n))
        self.assertNotIn("text", activity._fields, "no se guarda lo que se escribió")


@tagged("mirabilenet", "post_install", "-at_install")
class TestManualAndRoles(WhatsappCommon):

    def test_manual_send_goes_out_now(self):
        self.settings.daily_limit = 5
        charge = self._charge()
        message = self.Message.with_user(self.cobrador_n)._send_manual(
            charge, "recordatorio_pago")
        self.assertEqual(message.state, "enviado")
        self.assertIn("manual-%d-" % self.cobrador_n.id, message.unique_key)
        self.assertEqual(self.env["mirabilenet.audit.log"].search(
            [("res_id", "=", message.id), ("model", "=", "mirabilenet.whatsapp.message"),
             ("description", "ilike", "Envío manual")], limit=1).user_id, self.cobrador_n)

    def test_manual_send_respects_every_rule(self):
        charge = self._charge()
        Message = self.Message.with_user(self.cobrador_n)
        with self.assertRaises(UserError):
            Message._send_manual(charge, "aviso_vencido")  # todavía no venció
        with self.assertRaises(UserError):
            Message._send_manual(charge, "comprobante_verificado")
        with self.assertRaises(AccessError):
            self.Message.with_user(self.tecnico_n)._send_manual(charge, "recordatorio_pago")
        with self.assertRaises(AccessError):
            self.Message.with_user(self.cobrador_s)._send_manual(charge, "recordatorio_pago")
        self.env["mirabilenet.whatsapp.optout"].create({"partner_id": self.cliente.id})
        with self.assertRaises(UserError):
            Message._send_manual(charge, "recordatorio_pago")
        paid = self._charge(month=12)
        paid._mirabilenet_register_payment()
        with self.assertRaises(UserError):
            Message._send_manual(paid, "recordatorio_pago")

    def test_messages_are_isolated_by_region(self):
        north = self._charge().whatsapp_message_ids
        south = self._charge(partner=self.cliente_s).whatsapp_message_ids
        self.assertEqual(south.number_id, self.number_s)
        found = self.Message.with_user(self.cobrador_n).search([])
        self.assertIn(north, found)
        self.assertNotIn(south, found)
        with self.assertRaises(AccessError):
            south.with_user(self.cobrador_n).read(["destination"])
        with self.assertRaises(AccessError):
            self.Message.with_user(self.pasante).search([])
        self.assertIn(south, self.Message.with_user(self.auditor).search([]))
        otro_sur = self.env["res.partner"].create({
            "name": "Otro Sur", "mirabilenet_is_customer": True,
            "mirabilenet_region_id": self.sur.id})
        with self.assertRaises(AccessError):
            self.env["mirabilenet.whatsapp.consent"].with_user(self.cobrador_n).create(
                {"partner_id": otro_sur.id, "origin": "verbal", "detail": "x"})

    def test_configuration_roles(self):
        Number = self.env["mirabilenet.whatsapp.number"]
        with self.assertRaises(AccessError):
            self.number_n.with_user(self.cobrador_n).write({"sender_name": "x"})
        self.number_n.with_user(self.admin_n).write({"sender_name": "MIRABILENET Norte"})
        with self.assertRaises(AccessError):
            self.number_n.with_user(self.admin_n).write({"shared_global": True})
        self.number_s.with_user(self.gerencia).write({"shared_global": True})
        with self.assertRaises(ValidationError):
            self.number_n.with_user(self.gerencia).write({"shared_global": True})
        with self.assertRaises(AccessError):
            Number.with_user(self.admin_n).browse(self.number_s.id).read(["display_number"])
        with self.assertRaises(ValidationError):
            self.number_n.display_number = "70000001"
        with self.assertRaises(AccessError):
            self.settings.with_user(self.cobrador_n).write({"daily_limit": 99})
        self.settings.with_user(self.finanzas_n).write({"daily_limit": 3})

    def test_secrets_are_encrypted_and_hidden(self):
        self.assertFalse(self.settings.access_token)
        self.assertTrue(self.settings.has_access_token and self.settings.configured)
        self.assertNotIn("token-meta", self.settings.sudo().access_token_enc)
        self.assertEqual(self.settings._secret("access_token"), "token-meta")
        with self.assertRaises(AccessError):
            self.settings.with_user(self.finanzas_n).read(["access_token_enc"])
        with self.assertRaises(UserError):
            self.env["mirabilenet.whatsapp.settings"].create({})
        with self.assertRaises(UserError):
            self.settings.unlink()

    def test_template_rules(self):
        Template = self.env["mirabilenet.whatsapp.template"]
        with self.assertRaises(ValidationError):
            Template.create({"event": "pago_recibido", "meta_name": "x",
                             "variables": "cliente, contrasena"})
        with self.assertRaises(ValidationError):
            Template.create({"event": "aviso_emitido", "meta_name": "otra"})
        regional = Template.create({"event": "aviso_emitido", "meta_name": "aviso_norte",
                                    "region_id": self.norte.id, "variables": "cliente"})
        self.assertEqual(Template._for("aviso_emitido", self.norte), regional)
        self.assertEqual(Template._for("aviso_emitido", self.sur), self.tpl_emitido)

    def test_consent_is_never_created_in_bulk(self):
        Consent = self.env["mirabilenet.whatsapp.consent"].with_user(self.cobrador_n)
        partners = self.env["res.partner"].create([
            {"name": "A", "mirabilenet_is_customer": True,
             "mirabilenet_region_id": self.norte.id},
            {"name": "B", "mirabilenet_is_customer": True,
             "mirabilenet_region_id": self.norte.id}])
        with self.assertRaises(UserError):
            Consent.create([{"partner_id": p.id, "origin": "importacion", "detail": "lote"}
                            for p in partners])
        one = Consent.create({"partner_id": partners[0].id, "origin": "verbal",
                              "detail": "Llamada del 20/11", "user_id": self.gerencia.id})
        self.assertEqual(one.user_id, self.cobrador_n, "queda quien lo registró de verdad")

    def test_verify_number(self):
        FakeMetaGateway.numbers["PN-N"] = {"platform_type": "CLOUD_API", "is_on_biz_app": False}
        self.number_n.with_user(self.admin_n).action_verify()
        self.assertTrue(self.number_n.verified_at)
        self.assertEqual(self.number_n.meta_platform, "CLOUD_API · solo nube")
        FakeMetaGateway.fail_next("Token vencido", code="190")
        self.number_n.with_user(self.admin_n).action_verify()
        self.assertIn("Token vencido", self.number_n.last_error)
