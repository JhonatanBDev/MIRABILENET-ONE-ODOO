from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from ..siat import xsd_validator
from ..siat.gateway import FakeSiatGateway
from .common import MANAGER, MiraSiatCommon


@tagged("post_install", "-at_install", "mira_siat")
class TestSiatFlow(MiraSiatCommon):
    """Flujo fiscal completo contra el simulador, con dos contribuyentes."""

    # ---- emisión ----------------------------------------------------------
    def test_issue_valid_invoice(self):
        move = self._move()
        self.assertEqual(move.mira_siat_pos_id, self.pos_a)
        doc = self._issue(move)
        self.assertEqual(doc.state, "valid")
        self.assertEqual(doc.number, 1)
        self.assertEqual(doc.emission_type, "1")
        self.assertTrue(doc.cuf and doc.reception_code and doc.file_hash and doc.xml_sha256)
        self.assertTrue(doc.xsd_sha256)
        xml = doc.sudo().xml_attachment_id.raw
        self.assertTrue(xsd_validator.validate(xml, doc.xsd_id._content()))
        self.assertIn(doc.cuf.encode(), xml)
        self.assertIn(b"<montoTotal>200.00</montoTotal>", xml)
        self.assertIn("cuf=%s" % doc.cuf, doc.qr_url)
        self.assertEqual(doc.amount_in_words(), "Doscientos 00/100 Bolivianos")
        self.assertEqual(move.mira_siat_state, "valid")
        self.assertEqual(move.mira_siat_cuf, doc.cuf)
        html = self.env["ir.actions.report"]._render_qweb_html(
            "mira_sale_siat.report_mira_siat_invoice", doc.ids)[0].decode()
        self.assertIn(doc.cuf, html)
        self.assertIn("CLIENTE DEMO", html)
        self.assertIn("200.00", html)
        self.assertIn("SIN VALIDEZ FISCAL", html)
        audit =self.env["mira.siat.audit.log"].search(
            [("res_model", "=", "mira.siat.invoice"), ("res_id", "=", doc.id)])
        self.assertIn("invoice.issue", audit.mapped("action"))
        self.assertIn("invoice.valid", audit.mapped("action"))

    def test_idempotent_issue(self):
        move = self._move()
        first = self._issue(move)
        again = self.env["mira.siat.invoice"].with_user(self.cashier)._issue(
            move.with_user(self.cashier), first.idempotency_key)
        self.assertEqual(first, again)
        self.assertEqual(len(move.mira_siat_invoice_ids), 1)

    def test_sequence_is_per_point_of_sale(self):
        self.assertEqual(self._issue(self._move()).number, 1)
        self.assertEqual(self._issue(self._move()).number, 2)

    def test_lost_reply_never_duplicates(self):
        """El SIN aceptó pero la respuesta se perdió: consultar, no reemitir."""
        move = self._move()
        FakeSiatGateway.failures = ["lost_reply"]
        doc = self._issue(move)
        self.assertEqual(doc.state, "pending_retry")
        self.assertEqual(doc.error_code, "MS-SIAT-005")
        # Reintentar la emisión desde la venta devuelve el mismo documento.
        self.assertEqual(self._issue(move), doc)
        doc.with_user(self.cashier).action_retry()
        self.assertEqual(doc.state, "valid")
        self.assertEqual(len(move.mira_siat_invoice_ids), 1)
        self.assertEqual(doc.number, 1)

    def test_timeout_resends_same_file(self):
        """El SIN no recibió nada: se reenvía el MISMO archivo (número y CUF)."""
        move = self._move()
        FakeSiatGateway.failures = ["timeout"]
        doc = self._issue(move)
        self.assertEqual(doc.state, "pending_retry")
        cuf, number, file_hash = doc.cuf, doc.number, doc.file_hash
        doc.with_user(self.cashier).action_retry()
        self.assertEqual(doc.state, "valid")
        self.assertEqual((doc.cuf, doc.number, doc.file_hash), (cuf, number, file_hash))

    def test_rejection_keeps_evidence_and_allows_new_attempt(self):
        move = self._move()
        FakeSiatGateway.failures = ["reject"]
        rejected = self._issue(move)
        self.assertEqual(rejected.state, "rejected")
        self.assertEqual(rejected.error_code, "MS-SIAT-006")
        self.assertTrue(rejected.siat_messages)
        new = self._issue(move)
        self.assertNotEqual(new, rejected)
        self.assertEqual(new.state, "valid")
        self.assertEqual(new.number, rejected.number + 1)

    def test_validations_block_before_reserving_number(self):
        other = self.env["res.partner"].create({"name": "SIN DOCUMENTO"})
        move = self._move()
        move.button_draft()
        move.partner_id = other
        move.action_post()
        with self.assertRaises(UserError):
            self._issue(move)
        self.assertFalse(move.mira_siat_invoice_ids)
        self.assertEqual(self._issue(self._move()).number, 1)

    def test_no_xsd_no_send(self):
        self.env["mira.siat.xsd"].search([]).write({"active": False})
        with self.assertRaises(UserError) as ctx:
            self._issue(self._move())
        self.assertIn("MS-SIAT-004", str(ctx.exception))

    def test_suspended_tenant_is_blocked(self):
        self.company_a.mira_siat_association_status = "suspended"
        with self.assertRaises(UserError) as ctx:
            self._issue(self._move())
        self.assertIn("MS-TENANT-001", str(ctx.exception))

    # ---- inmutabilidad ----------------------------------------------------
    def test_fiscal_document_is_immutable(self):
        move = self._move()
        doc = self._issue(move)
        with self.assertRaises(UserError):
            doc.sudo().write({"number": 99})
        with self.assertRaises(UserError):
            doc.sudo().unlink()
        with self.assertRaises(UserError):
            move.button_draft()
        audit = self.env["mira.siat.audit.log"].search([], limit=1)
        with self.assertRaises(UserError):
            audit.sudo().write({"action": "x"})
        with self.assertRaises(UserError):
            audit.sudo().unlink()

    # ---- anulación y reversión -------------------------------------------
    def test_cancel_and_revert(self):
        doc = self._issue(self._move())
        reason = self._item(self.company_a, "motivo_anulacion")
        with self.assertRaises(AccessError):
            doc.with_user(self.cashier)._cancel(reason)
        self.assertEqual(doc.state, "valid")
        doc.with_user(self.supervisor)._cancel(reason)
        self.assertEqual(doc.state, "cancelled")
        self.assertEqual(doc.cancellation_reason_id, reason)
        doc.with_user(self.supervisor).action_revert_cancellation()
        self.assertEqual(doc.state, "valid")

    def test_cancel_rejected_by_sin_keeps_document_valid(self):
        doc = self._issue(self._move())
        FakeSiatGateway.failures = ["reject"]
        doc.with_user(self.supervisor)._cancel(self._item(self.company_a, "motivo_anulacion"))
        self.assertEqual(doc.state, "valid")
        self.assertEqual(doc.error_code, "MS-SIAT-006")

    def test_cancel_timeout_can_be_retried(self):
        doc = self._issue(self._move())
        FakeSiatGateway.failures = ["timeout"]
        doc.with_user(self.supervisor)._cancel(self._item(self.company_a, "motivo_anulacion"))
        self.assertEqual(doc.state, "cancellation_pending")
        doc.with_user(self.supervisor).action_retry()
        self.assertEqual(doc.state, "cancelled")

    # ---- contingencia -----------------------------------------------------
    def test_contingency_packages(self):
        self.company_a.mira_siat_package_size = 2
        event = self.env["mira.siat.event"].with_user(self.supervisor).create({
            "pos_id": self.pos_a.id,
            "event_type_id": self._item(self.company_a, "eventos_significativos").id,
            "description": "Corte de internet",
        })
        event.action_start()
        self.assertEqual(self.pos_a.connectivity_state, "contingency")
        docs = self.env["mira.siat.invoice"]
        for _i in range(3):
            docs |= self._issue(self._move())
        self.assertEqual(set(docs.mapped("state")), {"offline_issued"})
        self.assertEqual(set(docs.mapped("emission_type")), {"2"})
        self.assertEqual(docs.mapped("cufd_id"), event.cufd_id)
        event.action_close()
        self.pos_a.invalidate_recordset(["connectivity_state"])
        self.assertEqual(self.pos_a.connectivity_state, "online")
        event.action_register()
        self.assertTrue(event.reception_code)
        event.action_send_packages()
        self.assertEqual(len(event.package_ids), 2)
        self.assertEqual(sorted(event.package_ids.mapped("invoice_count")), [1, 2])
        self.assertEqual(set(docs.mapped("state")), {"package_sent"})
        event.action_validate_packages()
        self.assertEqual(set(docs.mapped("state")), {"package_validated"})
        self.assertEqual(event.state, "done")
        # Después de la contingencia se vuelve a emitir en línea.
        self.assertEqual(self._issue(self._move()).state, "valid")

    def test_observed_package_is_reconciled_per_invoice(self):
        event = self.env["mira.siat.event"].with_user(self.supervisor).create({
            "pos_id": self.pos_a.id,
            "event_type_id": self._item(self.company_a, "eventos_significativos").id,
            "description": "Corte de internet",
        })
        event.action_start()
        doc = self._issue(self._move())
        event.action_close()
        event.action_register()
        event.action_send_packages()
        FakeSiatGateway.failures = ["reject"]
        event.action_validate_packages()
        package = event.package_ids
        self.assertEqual(package.state, "observed")
        package.with_user(self.supervisor).action_reconcile()
        self.assertEqual(doc.state, "package_validated")
        self.assertEqual(event.state, "done")

    # ---- aislamiento multiempresa ----------------------------------------
    def test_tenant_isolation(self):
        doc = self._issue(self._move())
        Invoice = self.env["mira.siat.invoice"].with_user(self.cashier_b)
        self.assertFalse(Invoice.search([]))
        with self.assertRaises(AccessError):
            Invoice.browse(doc.id).read(["cuf"])
        with self.assertRaises(AccessError):
            self.env["mira.siat.pos"].with_user(self.cashier_b).browse(self.pos_a.id).read(["name"])
        with self.assertRaises(AccessError):
            self.env["mira.siat.branch"].with_user(self.cashier_b).browse(
                self.pos_a.branch_id.id).read(["name"])
        self.assertFalse(self.env["mira.siat.catalog.item"].with_user(self.cashier_b).search(
            [("company_id", "=", self.company_a.id)]))
        self.assertFalse(self.env["mira.siat.event"].with_user(self.cashier_b).search([]))
        # Las credenciales operativas son distintas por contribuyente.
        self.assertNotEqual(self.pos_a._get_cufd(), self.pos_b._get_cufd())
        self.assertNotEqual(self.pos_a._get_cuis()._code(), "")
        self.assertEqual(self.pos_a._get_cufd().company_id, self.company_a)

    def test_cannot_issue_with_foreign_point_of_sale(self):
        move = self._move()
        move.mira_siat_pos_id = self.pos_b
        with self.assertRaises(UserError):
            self.env["mira.siat.invoice"]._issue(move, "clave-cruzada")

    # ---- secretos ---------------------------------------------------------
    def test_secrets_are_encrypted_and_restricted(self):
        manager = new_test_user(
            self.env, "mira_admin", groups=MANAGER,
            company_id=self.company_a.id, company_ids=[(6, 0, self.company_a.ids)])
        with self.assertRaises(AccessError):
            self.company_a.with_user(self.cashier)._mira_siat_set_token("TOKEN-REAL", fields.Datetime.now())
        expires = fields.Datetime.add(fields.Datetime.now(), days=30)
        self.company_a.with_user(manager)._mira_siat_set_token("TOKEN-REAL", expires)
        stored = self.company_a.sudo().mira_siat_token_encrypted
        self.assertNotIn("TOKEN-REAL", stored)
        self.assertEqual(self.company_a._mira_siat_token(), "TOKEN-REAL")
        self.assertEqual(self.company_a.mira_siat_token_state, "valid")
        self.assertNotIn("TOKEN-REAL", self.company_a.mira_siat_token_fingerprint)
        # El campo cifrado no es legible para usuarios que no son de sistema.
        with self.assertRaises(AccessError):
            self.company_a.with_user(manager).read(["mira_siat_token_encrypted"])
        cufd = self.pos_a._get_cufd()
        self.assertNotIn(cufd._code(), cufd.sudo().code_encrypted)
        with self.assertRaises(AccessError):
            self.env["mira.siat.cufd"].with_user(self.cashier).browse(cufd.id).read(["valid_until"])
        audit = self.env["mira.siat.audit.log"].search([("action", "=", "token.set")])
        self.assertTrue(audit)
        self.assertNotIn("TOKEN-REAL", str(audit.read()))

    def test_simulator_forbidden_in_production(self):
        with self.assertRaises(Exception):
            self.company_a.mira_siat_environment = "1"
            self.company_a.flush_recordset()

    def test_card_number_is_masked(self):
        move = self._move(post=False)
        move.mira_siat_card_number = "4111 1111 1111 1234"
        self.assertEqual(move.mira_siat_card_number, "4111000000001234")
