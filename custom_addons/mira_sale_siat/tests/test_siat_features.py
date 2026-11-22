import datetime

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged

from ..siat import constants, xsd_validator
from ..siat.gateway import FakeSiatGateway
from ..siat.payment_methods import decompose
from .common import USER, MiraSiatCommon


@tagged("post_install", "-at_install", "mira_siat")
class TestSiatFeatures(MiraSiatCommon):
    """Nominatividad, métodos de pago, importes, sectores, notas, CAFC,
    fecha anterior, entrega al cliente y asistente."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cash = cls._code(cls.company_a, "tipo_metodo_pago", "1")
        cls.card = cls._code(cls.company_a, "tipo_metodo_pago", "2")
        cls.later = cls._code(cls.company_a, "tipo_metodo_pago", "6")
        cls.cash_card = cls._code(cls.company_a, "tipo_metodo_pago", "10")
        cls.gift = cls._code(cls.company_a, "tipo_metodo_pago", "27")
        cls.nit_type = cls._code(cls.company_a, "tipo_documento_identidad", "5")
        cls.backdater = new_test_user(
            cls.env, "mira_fecha_anterior",
            groups=USER + ",mira_sale_siat.group_mira_siat_supervisor,"
                          "mira_sale_siat.group_mira_siat_backdate",
            company_id=cls.company_a.id, company_ids=[(6, 0, cls.company_a.ids)])

    @classmethod
    def _code(cls, company, catalog_type, code):
        return cls.env["mira.siat.catalog.item"].search([
            ("company_id", "=", company.id), ("catalog_type", "=", catalog_type),
            ("code", "=", code)], limit=1)

    def _new_move(self, post=True, **vals):
        values = {
            "move_type": "out_invoice",
            "partner_id": self.customer.id,
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [(0, 0, {
                "product_id": self.product.id, "quantity": 1, "price_unit": 200.0,
                "tax_ids": [(6, 0, [])],
            })],
        }
        values.update(vals)
        move = self.env["account.move"].with_company(self.company_a).create(values)
        if post:
            move.action_post()
        return move

    def _pay(self, move, journal, amount=None):
        wizard = self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=move.ids).create(
                dict({"journal_id": journal.id}, **({"amount": amount} if amount else {})))
        wizard._create_payments()

    def _xml(self, doc):
        return doc.sudo().xml_attachment_id.raw

    # ================= Fase 1: cliente y nominatividad =================
    def test_reserved_nits_are_installed_and_protected(self):
        for xmlid, nit in (("partner_nit_99001", "99001"), ("partner_nit_99002", "99002"),
                           ("partner_nit_99003", "99003")):
            partner = self.env.ref("mira_sale_siat.%s" % xmlid)
            self.assertEqual(partner.vat, nit)
            self.assertTrue(partner.mira_siat_is_reserved_nit)
            with self.assertRaises(UserError):
                partner.unlink()

    def test_reserved_nit_forces_fixed_name_and_nit_type(self):
        control = self.env.ref("mira_sale_siat.partner_nit_99002")
        doc = self._issue(self._new_move(partner_id=control.id))
        self.assertEqual(doc.state, "valid")
        self.assertEqual(doc.payload["customer_name"], "CONTROL TRIBUTARIO")
        self.assertEqual(doc.payload["customer_doc_type"], constants.DOC_TYPE_NIT)
        self.assertFalse(doc.payload["customer_complement"])

    def test_foreigner_template_is_blocked_but_copies_work(self):
        template = self.env.ref("mira_sale_siat.partner_nit_99001")
        with self.assertRaises(UserError):
            self._issue(self._new_move(partner_id=template.id))
        foreigner = template.copy({"name": "ACME FOREIGN LLC"})
        doc = self._issue(self._new_move(partner_id=foreigner.id))
        self.assertEqual(doc.payload["customer_name"], "ACME FOREIGN LLC")
        self.assertEqual(doc.payload["customer_doc_number"], "99001")

    def test_nit_and_ci_must_be_numeric(self):
        partner = self.env["res.partner"].create({"name": "Con letras", "vat": "1234567"})
        partner.with_company(self.company_a).mira_siat_doc_type_id = self.nit_type
        with self.assertRaises(ValidationError):
            partner.with_company(self.company_a).vat = "12345A"
        passport = self._code(self.company_a, "tipo_documento_identidad", "3")
        partner.with_company(self.company_a).mira_siat_doc_type_id = passport
        partner.with_company(self.company_a).vat = "AB12345"
        doc = self._issue(self._new_move(partner_id=partner.id))
        self.assertEqual(doc.payload["customer_doc_number"], "AB12345")

    def test_legal_name_is_used_on_the_invoice(self):
        self.customer.mira_siat_legal_name = "RAZON SOCIAL FISCAL S.R.L."
        doc = self._issue(self._new_move())
        self.assertEqual(doc.payload["customer_name"], "RAZON SOCIAL FISCAL S.R.L.")

    def test_verify_nit(self):
        partner = self.customer.with_company(self.company_a).with_user(self.cashier)
        self.assertEqual(partner.action_mira_siat_verify_nit()["params"]["type"], "success")
        FakeSiatGateway.inactive_nits = {"1234567"}
        self.assertEqual(partner.action_mira_siat_verify_nit()["params"]["type"], "warning")
        reserved = self.env.ref("mira_sale_siat.partner_nit_99003").with_company(self.company_a)
        logs = self.env["mira.siat.log"].search_count([])
        self.assertEqual(reserved.action_mira_siat_verify_nit()["params"]["type"], "info")
        self.assertEqual(self.env["mira.siat.log"].search_count([]), logs)

    def test_force_invalid_nit_sends_exception_code(self):
        self.customer.with_company(self.company_a).mira_siat_doc_type_id = self.nit_type
        doc = self._issue(self._new_move(mira_siat_force_invalid_nit=True))
        self.assertEqual(doc.payload["exception_code"], 1)
        self.assertIn(b"<codigoExcepcion>1</codigoExcepcion>", self._xml(doc))

    # ================= Fase 2: método de pago =================
    def test_payment_method_decomposition(self):
        self.assertEqual(self.cash_card.components, "EFECTIVO|TARJETA")
        self.assertTrue(self.cash_card.includes_card)
        self.assertFalse(self.cash.includes_card)
        self.assertTrue(self.gift.includes_gift_card)
        combo = self._code(self.company_a, "tipo_metodo_pago", "35")
        self.assertEqual(combo.components, "EFECTIVO|GIFT-CARD")
        parsed = decompose({1: "EFECTIVO", 2: "TARJETA", 3: "TARJETA - EFECTIVO"})
        self.assertEqual(parsed[3], ["EFECTIVO", "TARJETA"])

    def test_credit_sale_declares_deferred_payment(self):
        self.company_a.mira_siat_credit_payment_method_id = self.later
        due = fields.Date.add(fields.Date.today(), days=30)
        move = self._new_move(invoice_date_due=due)
        self.assertEqual(move.mira_siat_suggested_method_id, self.later)
        doc = self._issue(move)
        self.assertEqual(doc.payload["payment_method_code"], 6)
        self.assertFalse(move.mira_siat_payment_method_manual)

    def test_cash_on_unpaid_credit_sale_is_blocked(self):
        due = fields.Date.add(fields.Date.today(), days=30)
        move = self._new_move(invoice_date_due=due)
        move.mira_siat_payment_method_id = self.cash
        self.assertTrue(move.mira_siat_payment_method_manual)
        with self.assertRaises(UserError):
            self._issue(move)

    def test_method_is_derived_from_payment_journals(self):
        bank = self.company_data["default_journal_bank"]
        cash = self.company_data["default_journal_cash"]
        cash.mira_siat_payment_method_id = self.cash
        bank.mira_siat_payment_method_id = self.card
        move = self._new_move()
        self._pay(move, cash, 80.0)
        self.assertEqual(move._mira_siat_derived_method(), self.cash)
        self._pay(move, bank, 120.0)
        self.assertEqual(move._mira_siat_derived_method(), self.cash_card)
        move.mira_siat_card_number = "4111-1111-1111-9999"
        doc = self._issue(move)
        self.assertEqual(doc.payload["payment_method_code"], 10)
        self.assertEqual(doc.payload["card_number"], "4111000000009999")

    def test_unmapped_journal_never_guesses(self):
        bank = self.company_data["default_journal_bank"]
        bank.mira_siat_payment_method_id = False
        move = self._new_move()
        self._pay(move, bank)
        self.assertFalse(move._mira_siat_derived_method())

    def test_manual_choice_is_respected(self):
        cash = self.company_data["default_journal_cash"]
        cash.mira_siat_payment_method_id = self.cash
        move = self._new_move()
        self._pay(move, cash)
        transfer = self._code(self.company_a, "tipo_metodo_pago", "7")
        move.mira_siat_payment_method_id = transfer
        doc = self._issue(move)
        self.assertEqual(doc.payload["payment_method_code"], 7)

    def test_card_is_required_and_masked(self):
        move = self._new_move()
        move.mira_siat_payment_method_id = self.card
        with self.assertRaises(UserError):
            self._issue(move)
        move.mira_siat_card_number = "4111********1234"
        self.assertEqual(move.mira_siat_card_number, "4111000000001234")
        doc = self._issue(move)
        self.assertIn(b"<numeroTarjeta>4111000000001234</numeroTarjeta>", self._xml(doc))

    def test_gift_card_reduces_the_vat_base(self):
        move = self._new_move()
        move.write({"mira_siat_payment_method_id": self.gift.id,
                    "mira_siat_gift_card_amount": 50.0})
        doc = self._issue(move)
        self.assertEqual(doc.payload["gift_card_amount"], "50.00")
        self.assertEqual(doc.payload["amount_total"], "200.00")
        self.assertEqual(doc.payload["amount_subject_to_vat"], "150.00")
        move2 = self._new_move()
        move2.write({"mira_siat_payment_method_id": self.gift.id,
                     "mira_siat_gift_card_amount": 500.0})
        with self.assertRaises(UserError):
            self._issue(move2)

    # ================= Fase 3: importes =================
    def test_global_discount(self):
        move = self._new_move(post=False)
        move.mira_siat_global_discount = 20.0
        move.action_mira_siat_apply_global_discount()
        move.action_mira_siat_apply_global_discount()  # idempotente: una sola línea
        discount_lines = move.invoice_line_ids.filtered(
            lambda l: l.product_id.mira_siat_is_discount)
        self.assertEqual(len(discount_lines), 1)
        self.assertEqual(move.amount_total, 180.0)
        move.action_post()
        doc = self._issue(move)
        self.assertEqual(doc.payload["additional_discount"], "20.00")
        self.assertEqual(doc.payload["amount_total"], "180.00")
        self.assertEqual(len(doc.payload["lines"]), 1)
        self.assertIn(b"<descuentoAdicional>20.00</descuentoAdicional>", self._xml(doc))

    def test_line_discount_and_full_discount(self):
        move = self._new_move(post=False)
        move.invoice_line_ids.discount = 10
        move.action_post()
        doc = self._issue(move)
        line = doc.payload["lines"][0]
        self.assertEqual((line["discount"], line["subtotal"]), ("20.00", "180.00"))
        full = self._new_move(post=False)
        full.invoice_line_ids = [(0, 0, {
            "product_id": self.product.id, "quantity": 1, "price_unit": 50.0,
            "discount": 100, "tax_ids": [(6, 0, [])]})]
        full.action_post()
        with self.assertRaises(UserError):
            self._issue(full)

    def test_foreign_currency_needs_mapping_and_converts(self):
        currency = self.setup_other_currency("EUR")
        move = self._new_move(currency_id=currency.id)
        with self.assertRaises(UserError):
            self._issue(move)
        self._code(self.company_a, "tipo_moneda", "2").currency_id = currency
        doc = self._issue(move)
        self.assertEqual(doc.state, "valid")
        self.assertEqual(doc.payload["currency_code"], 2)
        self.assertNotEqual(doc.payload["exchange_rate"], "1.00")
        self.assertEqual(doc.payload["amount_total_currency"], "200.00")
        rate = float(doc.payload["exchange_rate"])
        self.assertAlmostEqual(float(doc.payload["amount_total"]), 200.0 * rate, places=2)

    # ================= Fase 4: productos =================
    def test_homologation(self):
        template = self.product.product_tmpl_id.with_company(self.company_a)
        self.assertTrue(template.mira_siat_homologated)
        other = self.env["product.template"].with_company(self.company_a).create(
            {"name": "Sin homologar"})
        self.assertFalse(other.mira_siat_homologated)
        Template = self.env["product.template"].with_company(self.company_a)
        pending = Template.search([("mira_siat_homologated", "=", False)])
        self.assertIn(other, pending)
        self.assertNotIn(template, pending)
        discount = self.env.ref("mira_sale_siat.product_global_discount").product_tmpl_id
        self.assertTrue(discount.with_company(self.company_a).mira_siat_homologated)
        # La unidad por defecto de la empresa completa la homologación.
        template.mira_siat_unit_id = False
        self.assertFalse(template.mira_siat_homologated)
        self.company_a.mira_siat_default_unit_id = self._item(self.company_a, "unidad_medida")
        template.invalidate_recordset(["mira_siat_homologated"])
        self.assertTrue(template.mira_siat_homologated)
        self.assertEqual(self._issue(self._new_move()).state, "valid")

    def test_not_homologated_product_blocks_emission(self):
        product = self.env["product.product"].create({"name": "Nuevo", "type": "service"})
        move = self._new_move(invoice_line_ids=[(0, 0, {
            "product_id": product.id, "quantity": 1, "price_unit": 10.0,
            "tax_ids": [(6, 0, [])]})])
        with self.assertRaises(UserError):
            self._issue(move)

    # ================= Fase 5: puntos de venta =================
    def test_new_point_of_sale_is_registered_with_sin(self):
        pos = self.env["mira.siat.pos"].create({
            "branch_id": self.pos_a.branch_id.id, "name": "Caja 2", "register_new": True})
        self.assertLess(pos.code, 0)
        self.assertTrue(pos.pending_registration)
        move = self._new_move()
        move.mira_siat_pos_id = pos
        with self.assertRaises(UserError):
            self._issue(move)
        with self.assertRaises(UserError):
            pos.action_register()  # falta el tipo de punto de venta
        pos.pos_type_id = self._item(self.company_a, "tipo_punto_venta")
        pos.action_register()
        self.assertGreater(pos.code, 0)
        self.assertEqual(self._issue(move).state, "valid")
        pos.action_close_pos()
        self.assertFalse(pos.active)

    def test_rejected_registration_keeps_provisional_code(self):
        pos = self.env["mira.siat.pos"].create({
            "branch_id": self.pos_a.branch_id.id, "name": "Caja 3", "register_new": True,
            "pos_type_id": self._item(self.company_a, "tipo_punto_venta").id})
        FakeSiatGateway.failures = ["reject"]
        with self.assertRaises(UserError):
            pos.action_register()
        self.assertLess(pos.code, 0)

    def test_single_default_point_of_sale(self):
        self.pos_a.is_default = True
        with self.assertRaises(ValidationError):
            self.env["mira.siat.pos"].create({
                "branch_id": self.pos_a.branch_id.id, "name": "Otra", "code": 7,
                "is_default": True})

    # ================= Fase 6: telecomunicaciones =================
    def test_telecom_invoice(self):
        move = self._new_move(mira_siat_sector="22", mira_siat_joint_nit="1020304050")
        doc = self._issue(move)
        self.assertEqual(doc.state, "valid")
        self.assertEqual(doc.sector_code, constants.SECTOR_TELECOM)
        xml = self._xml(doc)
        self.assertIn(b"<facturaComputarizadaTelecomunicacion", xml)
        self.assertIn(b"<nitConjunto>1020304050</nitConjunto>", xml)
        self.assertIn(b"<codigoDocumentoSector>22</codigoDocumentoSector>", xml)
        self.assertTrue(xsd_validator.validate(xml, doc.xsd_id._content()))
        self.assertEqual(doc.xsd_id.sector_code, 22)
        # Cada sector lleva su propia numeración.
        self.assertEqual(doc.number, 1)
        self.assertEqual(self._issue(self._new_move()).number, 1)
        self.assertEqual(self._issue(self._new_move(mira_siat_sector="22")).number, 2)

    def test_sector_defaults_from_company_and_journal(self):
        self.company_a.mira_siat_default_sector = "22"
        self.assertEqual(self._new_move(post=False).mira_siat_sector, "22")
        self.company_data["default_journal_sale"].mira_siat_sector = "1"
        self.assertEqual(self._new_move(post=False).mira_siat_sector, "1")

    def test_activity_must_allow_the_sector(self):
        self.env["mira.siat.catalog.item"].search([
            ("company_id", "=", self.company_a.id),
            ("catalog_type", "=", "actividades_documento_sector"), ("code", "=", "22"),
        ]).write({"active": False})
        with self.assertRaises(UserError):
            self._issue(self._new_move(mira_siat_sector="22"))

    # ================= Fase 7: nota de crédito-débito =================
    def _refund(self, move):
        refund = move._reverse_moves([{"invoice_date": fields.Date.today()}])
        refund.action_post()
        return refund

    def test_credit_note(self):
        move = self._new_move()
        invoice = self._issue(move)
        note = self._issue(self._refund(move))
        self.assertEqual(note.state, "valid")
        self.assertEqual(note.sector_code, constants.SECTOR_CREDIT_DEBIT_NOTE)
        self.assertEqual(note.invoice_type, constants.INVOICE_TYPE_ADJUSTMENT)
        self.assertEqual(note.document_kind, "note")
        self.assertTrue(note.name.startswith("NC-"))
        self.assertEqual(note.original_invoice_id, invoice)
        payload = note.payload
        self.assertEqual(payload["original_cuf"], invoice.cuf)
        self.assertEqual(payload["amount_returned"], "200.00")
        self.assertEqual(payload["amount_effective"], "26.00")
        self.assertEqual([l["transaction_code"] for l in payload["lines"]], [1, 2])
        xml = self._xml(note)
        self.assertIn(b"<notaFiscalComputarizadaCreditoDebito", xml)
        self.assertTrue(xsd_validator.validate(xml, note.xsd_id._content()))
        # Una factura con nota vigente no se anula; la nota sí.
        reason = self._item(self.company_a, "motivo_anulacion")
        with self.assertRaises(UserError):
            invoice.with_user(self.supervisor)._cancel(reason)
        note.with_user(self.supervisor)._cancel(reason)
        self.assertEqual(note.state, "cancelled")
        invoice.with_user(self.supervisor)._cancel(reason)
        self.assertEqual(invoice.state, "cancelled")

    def test_credit_note_requires_accepted_original(self):
        move = self._new_move()
        with self.assertRaises(UserError):
            self._issue(self._refund(move))

    def test_credit_note_must_match_original_items(self):
        move = self._new_move()
        self._issue(move)
        refund = move._reverse_moves([{"invoice_date": fields.Date.today()}])
        refund.invoice_line_ids.quantity = 3
        refund.action_post()
        with self.assertRaises(UserError):
            self._issue(refund)

    # ================= Fase 8: CAFC y fecha anterior =================
    def _past_event(self, user, cafc=None, hours_ago=3):
        now = fields.Datetime.now()
        event = self.env["mira.siat.event"].with_user(user).create({
            "pos_id": self.pos_a.id, "kind": "past",
            "event_type_id": self._item(self.company_a, "eventos_significativos").id,
            "description": "Corte de energía",
            "start_at": now - datetime.timedelta(hours=hours_ago),
            "end_at": now - datetime.timedelta(minutes=5),
            "cafc_id": cafc.id if cafc else False,
        })
        event.action_start()
        return event

    def test_manual_invoice_with_cafc(self):
        cafc = self.env["mira.siat.cafc"].create({
            "name": "1011917833B0D", "pos_id": self.pos_a.id,
            "number_from": 100, "number_to": 102})
        self.assertEqual(cafc.available_count, 3)
        event = self._past_event(self.supervisor, cafc)
        # Una regularización no pone al punto de venta en contingencia.
        self.assertEqual(self.pos_a.connectivity_state, "online")
        paper_date = fields.Datetime.now() - datetime.timedelta(hours=1)
        move = self._new_move(mira_siat_manual=True, mira_siat_manual_number=101,
                              mira_siat_manual_date=paper_date)
        doc = self._issue(move)
        self.assertEqual(doc.state, "offline_issued")
        self.assertEqual((doc.number, doc.number_series), (101, cafc.name))
        self.assertEqual(doc.cafc_id, cafc)
        self.assertEqual(doc.emission_date, paper_date.replace(microsecond=0))
        self.assertIn(b"<cafc>1011917833B0D</cafc>", self._xml(doc))
        self.assertEqual((cafc.used_count, cafc.available_count), (1, 2))
        for number in (101, 99):  # repetido y fuera de rango
            bad = self._new_move(mira_siat_manual=True, mira_siat_manual_number=number,
                                 mira_siat_manual_date=paper_date)
            with self.assertRaises(UserError):
                self._issue(bad)
        # Una venta normal sigue saliendo en línea mientras tanto.
        self.assertEqual(self._issue(self._new_move()).state, "valid")
        event.action_close()
        event.action_register()
        event.action_send_packages()
        event.action_validate_packages()
        self.assertEqual(doc.state, "package_validated")
        self.assertEqual(event.state, "done")

    def test_backdated_emission_requires_authorization(self):
        when = fields.Datetime.now() - datetime.timedelta(hours=1)
        self._past_event(self.supervisor)
        move = self._new_move(mira_siat_backdate=when)
        with self.assertRaises(AccessError):  # sin el grupo
            self._issue(move, self.cashier)
        with self.assertRaises(UserError):  # con grupo pero sin autorización
            self._issue(move, self.backdater)
        Auth = self.env["mira.siat.retro.authorization"]
        with self.assertRaises(AccessError):
            Auth.with_user(self.cashier).create({"reason": "x"})
        auth = Auth.with_user(self.backdater).create({"reason": "Caída del servidor"})
        self.assertTrue(auth.is_current)
        self.assertTrue(move.with_user(self.backdater).mira_siat_can_backdate)
        self.assertFalse(move.with_user(self.cashier).mira_siat_can_backdate)
        doc = self._issue(move, self.backdater)
        self.assertEqual(doc.state, "offline_issued")
        self.assertEqual(doc.retro_authorization_id, auth)
        self.assertEqual(doc.emission_type, "2")
        self.assertEqual(doc.number_series, "S")
        auth.action_close()
        self.assertFalse(auth.is_current)
        with self.assertRaises(UserError):
            auth.sudo().unlink()

    def test_backdate_limits(self):
        Auth = self.env["mira.siat.retro.authorization"].with_user(self.backdater)
        now = fields.Datetime.now()
        with self.assertRaises(ValidationError):
            Auth.create({"reason": "larga", "start_at": now,
                         "end_at": now + datetime.timedelta(hours=49)})
        Auth.create({"reason": "ok"})
        self.company_a.mira_siat_backdate_max_hours = 2
        self._past_event(self.supervisor, hours_ago=6)
        old = self._new_move(mira_siat_backdate=now - datetime.timedelta(hours=4))
        with self.assertRaises(UserError):
            self._issue(old, self.backdater)
        future = self._new_move(mira_siat_backdate=now + datetime.timedelta(hours=1))
        with self.assertRaises(UserError):
            self._issue(future, self.backdater)
        with self.assertRaises(ValidationError):
            self.company_a.mira_siat_backdate_max_hours = 72

    # ================= Fase 9: entrega al cliente =================
    def test_email_and_ticket(self):
        self.customer.email = "cliente@example.com"
        doc = self._issue(self._new_move())
        self.assertTrue(doc.email_sent_at)
        mail = self.env["mail.mail"].sudo().search(
            [("model", "=", "mira.siat.invoice"), ("res_id", "=", doc.id)])
        self.assertEqual(len(mail), 1)
        names = mail.attachment_ids.mapped("name")
        self.assertTrue(any(name.endswith(".xml") for name in names))
        self.assertIn(str(doc.number), mail.subject)
        html = self.env["ir.actions.report"]._render_qweb_html(
            "mira_sale_siat.report_mira_siat_ticket", doc.ids)[0].decode()
        self.assertIn(doc.cuf, html)
        doc.with_user(self.supervisor)._cancel(self._item(self.company_a, "motivo_anulacion"))
        notices = self.env["mail.mail"].sudo().search(
            [("model", "=", "mira.siat.invoice"), ("res_id", "=", doc.id)])
        self.assertEqual(len(notices), 2)

    def test_no_email_does_not_block_emission(self):
        self.customer.email = False
        doc = self._issue(self._new_move())
        self.assertEqual(doc.state, "valid")
        self.assertFalse(doc.email_sent_at)
        with self.assertRaises(UserError):
            doc.with_user(self.cashier).action_send_email()

    # ================= Fase 10: asistente =================
    def test_config_wizard_end_to_end(self):
        company = self.setup_other_company(name="Empresa nueva")["company"]
        Wizard = self.env["mira.siat.config.wizard"].with_company(company)
        wizard = Wizard.create({})
        self.assertEqual(wizard.step, "company")
        with self.assertRaises(UserError):  # no se avanza sin NIT
            wizard.action_next()
        wizard.nit = "3005791240"
        wizard.action_next()
        self.assertEqual(wizard.step, "connection")
        self.assertTrue(company.mira_siat_enabled)
        wizard.action_next()
        self.assertEqual(company.mira_siat_association_status, "associated")
        self.assertEqual(wizard.step, "branches")
        wizard.branch_ids.write({"address": "Calle 1", "municipality": "Tarija",
                                 "pos_count": 2})
        wizard.action_next()
        # El simulador no usa token: ese paso se omite.
        self.assertEqual(wizard.step, "sync")
        points = self.env["mira.siat.pos"].search([("company_id", "=", company.id)])
        self.assertEqual(sorted(p.code >= 0 for p in points), [False, True])
        self.assertTrue(company._mira_siat_default_pos())
        wizard.action_next()
        self.assertEqual(wizard.step, "defaults")
        self.assertTrue(all(p.code >= 0 and p.cufd_valid_until for p in points))
        self.assertTrue(self.env["mira.siat.catalog"].search_count(
            [("company_id", "=", company.id)]))
        with self.assertRaises(UserError):  # faltan moneda y método de pago
            wizard.action_next()
        wizard.currency_item_id = self._code(company, "tipo_moneda", "1")
        wizard.default_payment_method_id = self._code(company, "tipo_metodo_pago", "1")
        wizard.action_next()
        self.assertEqual(wizard.step, "done")
        self.assertEqual(company.mira_siat_currency_item_id.currency_id, company.currency_id)
        wizard.action_back()
        self.assertEqual(wizard.step, "defaults")

    def test_config_wizard_warns_in_production(self):
        wizard = self.env["mira.siat.config.wizard"].with_company(self.company_a).create({})
        wizard.step = "sync"
        self.assertIn("simulador", wizard.notice)
        self.assertFalse(wizard.is_production)
        self.assertEqual(len(wizard.branch_ids), 1)
        self.assertEqual(wizard.branch_ids.existing_count, 1)
