from datetime import date, timedelta

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from ..models.contract_contract import next_day_of_month


@tagged("mirabilenet", "post_install", "-at_install")
class TestContratos(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # La clase base deja un contador como usuario; la preparación es del sistema.
        cls.env = cls.env(user=cls.env.ref("base.user_root"))
        Region = cls.env["mirabilenet.region"]
        company = cls.env.company
        common = {"company_id": company.id, "currency_id": company.currency_id.id,
                  "dia_emision": 5, "dia_emision_prepago": 1, "dia_vencimiento": 15,
                  "dias_gracia": 3, "hora_corte": 9.0, "suspension_automatica": True,
                  "reactivacion_automatica": True}
        cls.norte = Region.create(dict(common, code="C-N", name="Norte cobros", wg_region_id=55))
        cls.sur = Region.create(dict(common, code="C-S", name="Sur cobros", wg_region_id=56))
        Partner = cls.env["res.partner"]
        cls.cliente = Partner.create({"name": "Cliente Norte", "mirabilenet_is_customer": True,
                                      "mirabilenet_region_id": cls.norte.id})
        cls.cliente_s = Partner.create({"name": "Cliente Sur", "mirabilenet_is_customer": True,
                                        "mirabilenet_region_id": cls.sur.id})
        cls.plan = cls.env["product.template"].create({
            "name": "Hogar 20", "type": "service", "mirabilenet_is_plan": True,
            "mirabilenet_plan_code": "C-HOGAR", "list_price": 300,
            "mirabilenet_down_mbps": 20, "mirabilenet_up_mbps": 10})
        cls.finanzas_n = cls._user("c_finanzas_n", "finanzas", cls.norte)
        cls.cajero_s = cls._user("c_cajero_s", "cajero", cls.sur)
        cls.gerencia = cls._user("c_gerencia", "gerencia")

    @classmethod
    def _user(cls, login, role, region=None):
        user = new_test_user(cls.env, login, groups="base.group_user")
        user.write({"mirabilenet_role": role,
                    "mirabilenet_region_id": region.id if region else False})
        return user

    def _service(self, partner=None, mode="pospago", activation=date(2026, 3, 10), price=None):
        partner = partner or self.cliente
        vals = {"partner_id": partner.id, "plan_id": self.plan.id, "payment_mode": mode}
        if price is not None:
            vals["monthly_price"] = price
        service = self.env["mirabilenet.service"].create(vals)
        service.state = "activo"
        service._mirabilenet_ensure_contract(activation)
        return service

    def _emit(self, service, on):
        self.env["contract.contract"].cron_recurring_create_invoice(on)
        return service.invoice_ids

    def _pay(self, invoice, amount=None):
        wizard = self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=invoice.ids).create(
            {"amount": amount or invoice.amount_residual})
        return wizard._create_payments()

    # ------------------------------------------------------------------
    def test_day_helper(self):
        self.assertEqual(next_day_of_month(date(2026, 3, 10), 5), date(2026, 4, 5))
        self.assertEqual(next_day_of_month(date(2026, 3, 5), 5), date(2026, 3, 5))
        self.assertEqual(next_day_of_month(date(2026, 12, 20), 15), date(2027, 1, 15))
        self.assertEqual(next_day_of_month(date(2026, 2, 1), 31), date(2026, 2, 28))

    def test_contract_is_created_once_from_the_service(self):
        service = self._service()
        contract = service.contract_id
        self.assertEqual(contract.partner_id, self.cliente)
        self.assertEqual(contract.mirabilenet_region_id, self.norte)
        line = contract.contract_line_ids
        # Pospago: meses enteros contados desde el día del alta, sin prorrateo.
        self.assertEqual((line.price_unit, line.recurring_rule_type, line.qty_type,
                          line.recurring_invoicing_type),
                         (300, "monthly", "fixed", "post-paid"))
        self.assertEqual(line.date_start, date(2026, 3, 10))
        # El contrato empieza el día del alta, no el día en que se creó en Odoo.
        self.assertEqual(contract.date_start, date(2026, 3, 10))
        self.assertEqual(service.date_start, date(2026, 3, 10))
        self.assertEqual(service._mirabilenet_ensure_contract(), contract)
        service.monthly_price = 350
        self.assertEqual(line.price_unit, 350)
        prepaid = self._service(mode="prepago")
        self.assertEqual(prepaid.contract_id.contract_line_ids.recurring_invoicing_type,
                         "pre-paid")

    def test_first_month_is_prorated_then_full_calendar_months(self):
        prepaid = self._service(mode="prepago")  # alta el 10 de marzo
        self.assertFalse(self._emit(prepaid, date(2026, 3, 9)))
        first = self._emit(prepaid, date(2026, 3, 10))
        self.assertEqual(len(first), 1)
        self.assertEqual((first.state, first.move_type), ("posted", "out_invoice"))
        self.assertEqual(first.mirabilenet_region_id, self.norte)
        self.assertEqual((first.invoice_date, first.invoice_date_due),
                         (date(2026, 3, 10), date(2026, 3, 15)))
        # 22 de los 31 días de marzo.
        self.assertAlmostEqual(first.amount_untaxed, 300 * 22 / 31, delta=0.5)
        self.assertEqual(prepaid.amount_due, first.amount_residual)
        self.assertEqual(self.cliente.mirabilenet_balance, first.amount_residual)
        # Emitir dos veces el mismo día no duplica; abril ya es un mes completo.
        self.assertEqual(len(self._emit(prepaid, date(2026, 3, 10))), 1)
        second = self._emit(prepaid, date(2026, 4, 1)) - first
        self.assertEqual((second.amount_untaxed, second.invoice_date_due),
                         (300, date(2026, 4, 15)))

    def test_postpaid_is_billed_every_month_on_the_activation_day(self):
        # Alta el 10 de marzo: paga el 10 de cada mes, el mes entero, y vence ese mismo día.
        postpaid = self._service(partner=self.cliente_s, mode="pospago")
        self.assertEqual(postpaid.billing_day, 10)
        self.assertFalse(self._emit(postpaid, date(2026, 3, 31)))
        self.assertFalse(self._emit(postpaid, date(2026, 4, 9)))
        april = self._emit(postpaid, date(2026, 4, 10))
        self.assertEqual(len(april), 1)
        self.assertEqual((april.invoice_date, april.invoice_date_due, april.amount_untaxed),
                         (date(2026, 4, 10), date(2026, 4, 10), 300))
        self.assertEqual(april.mirabilenet_region_id, self.sur)
        self.assertFalse(self._emit(postpaid, date(2026, 5, 9)) - april)
        may = self._emit(postpaid, date(2026, 5, 10)) - april
        self.assertEqual((may.invoice_date, may.amount_untaxed), (date(2026, 5, 10), 300))
        # Un alta el 3 de noviembre paga el 3 de diciembre, de enero, de febrero...
        november = self._service(mode="pospago", activation=date(2026, 11, 3))
        self.assertEqual(november.billing_day, 3)
        self.assertEqual(november.contract_id.contract_line_ids.recurring_next_date,
                         date(2026, 12, 3))
        self._emit(november, date(2026, 12, 3))
        self.assertEqual(november.contract_id.contract_line_ids.recurring_next_date,
                         date(2027, 1, 3))

    def test_postpaid_activated_at_month_end_settles_on_a_day_every_month_has(self):
        # Febrero no tiene 31: el cobro pasa al 28 y se queda ahí, sin perder ni repetir días.
        service = self._service(mode="pospago", activation=date(2026, 1, 31))
        line = service.contract_id.contract_line_ids
        self.assertEqual(line.recurring_next_date, date(2026, 2, 28))
        self._emit(service, date(2026, 2, 28))
        self.assertEqual(line.recurring_next_date, date(2026, 3, 28))

    def test_prepaid_is_notified_to_everyone_on_the_region_day(self):
        self.assertEqual(self._service(mode="prepago").billing_day, 1)
        self.norte.dia_emision_prepago = 5
        prepaid = self._service(mode="prepago", activation=date(2026, 3, 1))
        self.assertEqual(prepaid.billing_day, 5)
        self.assertFalse(self._emit(prepaid, date(2026, 3, 4)))
        march = self._emit(prepaid, date(2026, 3, 5))
        self.assertEqual((march.invoice_date, march.amount_untaxed), (date(2026, 3, 5), 300))
        self.assertFalse(self._emit(prepaid, date(2026, 4, 4)) - march)
        april = self._emit(prepaid, date(2026, 4, 5)) - march
        self.assertEqual((april.invoice_date, april.amount_untaxed), (date(2026, 4, 5), 300))
        # Cambiar el día en la región mueve el próximo aviso de todos sus servicios.
        self.norte.dia_emision_prepago = 1
        self.assertEqual(prepaid.contract_id.contract_line_ids.recurring_next_date,
                         date(2026, 5, 1))
        self.assertEqual(prepaid.billing_day, 1)

    def test_cut_respects_grace_days_and_payment_reactivates(self):
        service = self._service(mode="prepago")
        invoice = self._emit(service, date(2026, 3, 10))  # vence el 15 de marzo
        Region = self.env["mirabilenet.region"]
        self.assertEqual(Region._cron_scheduled_cuts(hour=9, today=date(2026, 3, 18)), 0)
        self.assertEqual(Region._cron_scheduled_cuts(hour=8, today=date(2026, 3, 19)), 0)
        self.assertEqual(Region._cron_scheduled_cuts(hour=9, today=date(2026, 3, 19)), 1)
        self.assertEqual(Region._cron_scheduled_cuts(hour=9, today=date(2026, 3, 19)), 0)
        order = service.transition_ids.filtered(lambda t: t.action == "suspender")
        self.assertEqual(len(order), 1)
        # El estado solo cambia cuando el equipo confirma; aquí se simula esa confirmación.
        service.state = "suspendido"
        self._pay(invoice, amount=100)
        self.assertFalse(service.transition_ids.filtered(lambda t: t.action == "activar"))
        self._pay(invoice)
        self.assertIn(invoice.payment_state, ("paid", "in_payment"))
        self.assertEqual(len(service.transition_ids.filtered(lambda t: t.action == "activar")), 1)
        self.assertEqual(self.cliente.mirabilenet_balance, 0)
        # Sin corte automático en la región, no se corta.
        self.norte.suspension_automatica = False
        other = self._service(mode="prepago", activation=date(2026, 6, 20))
        self._emit(other, date(2026, 6, 20))
        self.assertEqual(Region._cron_scheduled_cuts(hour=9, today=date(2026, 8, 30)), 0)

    def test_termination_stops_the_contract(self):
        today = fields.Date.today()
        running = self._service(mode="prepago")
        self._emit(running, date(2026, 3, 10))
        running._apply_confirmed_state("baja")
        self.assertEqual(running.contract_id.contract_line_ids.date_end, today)
        # De baja antes de que empiece a cobrarse: el contrato se archiva y nunca emite.
        unborn = self._service(partner=self.cliente_s, mode="prepago",
                               activation=today + timedelta(days=1))
        unborn._apply_confirmed_state("baja")
        self.assertFalse(unborn.contract_id.active)
        self.assertFalse(self._emit(unborn, today + timedelta(days=400)))

    def test_invoices_and_payments_are_isolated_by_region(self):
        north = self._emit(self._service(mode="prepago"), date(2026, 3, 10))
        south = self._emit(self._service(partner=self.cliente_s, mode="prepago"),
                           date(2026, 3, 10))
        Move = self.env["account.move"]
        domain = [("id", "in", (north | south).ids)]
        self.assertEqual(Move.with_user(self.finanzas_n).search(domain), north)
        self.assertEqual(Move.with_user(self.cajero_s).search(domain), south)
        self.assertEqual(Move.with_user(self.gerencia).search(domain), north | south)
        with self.assertRaises(AccessError):
            north.with_user(self.cajero_s).read(["amount_total"])
        payment = self._pay(north)
        self.assertEqual(payment.mirabilenet_region_id, self.norte)
        Payment = self.env["account.payment"]
        self.assertFalse(Payment.with_user(self.cajero_s).search([("id", "=", payment.id)]))
        self.assertEqual(Payment.with_user(self.finanzas_n).search([("id", "=", payment.id)]),
                         payment)
        Contract = self.env["contract.contract"]
        self.assertFalse(Contract.with_user(self.cajero_s).search(
            [("mirabilenet_region_id", "=", self.norte.id)]))
        # Una factura hecha a mano toma la región del cliente.
        manual = Move.create({"move_type": "out_invoice", "partner_id": self.cliente_s.id})
        self.assertEqual(manual.mirabilenet_region_id, self.sur)
