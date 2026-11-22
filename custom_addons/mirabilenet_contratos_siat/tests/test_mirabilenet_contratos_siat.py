from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.mirabilenet_contratos.tests.test_mirabilenet_contratos import TestContratos


@tagged("mirabilenet", "post_install", "-at_install")
class TestContratosSiat(TestContratos):

    def _issuer(self, calls, state="accepted", fail=False):
        def _issue(model, move, key):
            calls.append((move, model.env.user))
            if fail:
                raise RuntimeError("SIN sin conexión")
            return SimpleNamespace(state=state)
        return patch.object(type(self.env["mira.siat.invoice"]), "_issue", _issue)

    def test_fiscal_invoice_is_issued_when_the_invoice_gets_paid(self):
        invoice = self._emit(self._service(mode="prepago"), date(2026, 3, 10))
        calls = []
        with self._issuer(calls):
            self._pay(invoice)
            self.assertFalse(calls, "apagado en la empresa, no se emite sola")
            self.env.company.mirabilenet_invoice_on_payment = True
            other = self._emit(self._service(partner=self.cliente_s, mode="prepago"),
                               date(2026, 3, 10))
            self._pay(other, amount=50)
            self.assertFalse(calls, "un pago parcial no emite")
            self._pay(other)
        self.assertEqual([move for move, _user in calls], [other])
        self.assertEqual(other.mirabilenet_fiscal_user_id, self.env.user)
        self.assertFalse(other.mirabilenet_fiscal_pending)

    def test_a_fiscal_failure_never_undoes_the_payment(self):
        self.env.company.mirabilenet_invoice_on_payment = True
        invoice = self._emit(self._service(mode="prepago"), date(2026, 3, 10))
        calls = []
        with self._issuer(calls, fail=True):
            payment = self._pay(invoice)
        self.assertIn(invoice.payment_state, ("paid", "in_payment"))
        self.assertTrue(payment.exists())
        self.assertTrue(invoice.mirabilenet_fiscal_pending)
        self.assertIn("SIN sin conexión", invoice.mirabilenet_fiscal_error)
        with self._issuer(calls, state="rejected"):
            self.assertEqual(self.env["account.move"]._cron_emit_fiscal_invoices(), 0)
        self.assertTrue(invoice.mirabilenet_fiscal_pending)
        with self._issuer(calls):
            self.assertEqual(self.env["account.move"]._cron_emit_fiscal_invoices(), 1)
        self.assertFalse(invoice.mirabilenet_fiscal_pending)
        self.assertFalse(invoice.mirabilenet_fiscal_error)
