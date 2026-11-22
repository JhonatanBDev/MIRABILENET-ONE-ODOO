import os
from unittest.mock import patch

from odoo import fields
from odoo.tests import new_test_user

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from ..siat.gateway import FakeSiatGateway

USER = "account.group_account_invoice,mira_sale_siat.group_mira_siat_user"
SUPERVISOR = "account.group_account_invoice,mira_sale_siat.group_mira_siat_supervisor"
MANAGER = "account.group_account_invoice,mira_sale_siat.group_mira_siat_manager"


class MiraSiatCommon(AccountTestInvoicingCommon):
    """Dos contribuyentes configurados contra el simulador."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.startClassPatcher(patch.dict(os.environ, {"MIRA_SIAT_MASTER_KEY": "clave-de-prueba"}))
        FakeSiatGateway.reset()
        cls.env.user.group_ids |= cls.env.ref("mira_sale_siat.group_mira_siat_manager")
        cls.company_a = cls.company_data["company"]
        cls.company_b = cls.setup_other_company()["company"]
        cls.pos_a = cls._setup_tenant(cls.company_a, "1003579028")
        cls.pos_b = cls._setup_tenant(cls.company_b, "2004680139")
        cls.cashier = new_test_user(
            cls.env, "mira_cajero", groups=USER,
            company_id=cls.company_a.id, company_ids=[(6, 0, cls.company_a.ids)])
        cls.supervisor = new_test_user(
            cls.env, "mira_supervisor", groups=SUPERVISOR,
            company_id=cls.company_a.id, company_ids=[(6, 0, cls.company_a.ids)])
        cls.cashier_b = new_test_user(
            cls.env, "mira_cajero_b", groups=USER,
            company_id=cls.company_b.id, company_ids=[(6, 0, cls.company_b.ids)])
        cls.customer = cls.env["res.partner"].create({"name": "CLIENTE DEMO", "vat": "1234567"})
        cls._map_partner(cls.customer, cls.company_a)
        cls.product = cls.env["product.product"].create({
            "name": "Servicio mensual 50 Mbps", "default_code": "PLAN-50",
            "type": "service", "list_price": 200.0,
        })
        cls._map_product(cls.product, cls.company_a)

    @classmethod
    def _item(cls, company, catalog_type):
        return cls.env["mira.siat.catalog.item"].search(
            [("company_id", "=", company.id), ("catalog_type", "=", catalog_type)], limit=1)

    @classmethod
    def _setup_tenant(cls, company, nit):
        company.write({
            "vat": nit,
            "mira_siat_enabled": True,
            "mira_siat_association_status": "associated",
            "mira_siat_gateway_mode": "fake",
        })
        branch = cls.env["mira.siat.branch"].create({
            "company_id": company.id, "code": 0, "name": "CASA MATRIZ",
            "address": "Av. Siempre Viva 123", "municipality": "La Paz",
        })
        pos = cls.env["mira.siat.pos"].create(
            {"branch_id": branch.id, "code": 0, "name": "Caja 1"})
        pos.action_sync_catalogs()
        pos.action_refresh_cufd()
        company.write({
            "mira_siat_currency_item_id": cls._item(company, "tipo_moneda").id,
            "mira_siat_default_payment_method_id": cls._item(company, "tipo_metodo_pago").id,
        })
        return pos

    @classmethod
    def _map_partner(cls, partner, company):
        partner.with_company(company).mira_siat_doc_type_id = cls._item(
            company, "tipo_documento_identidad")

    @classmethod
    def _map_product(cls, product, company):
        product.product_tmpl_id.with_company(company).write({
            "mira_siat_activity_id": cls._item(company, "actividades").id,
            "mira_siat_product_id": cls._item(company, "productos_servicios").id,
            "mira_siat_unit_id": cls._item(company, "unidad_medida").id,
        })

    def setUp(self):
        super().setUp()
        FakeSiatGateway.failures = []

    def _move(self, company=None, post=True):
        company = company or self.company_a
        move = self.env["account.move"].with_company(company).create({
            "move_type": "out_invoice",
            "partner_id": self.customer.id,
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [(0, 0, {
                "product_id": self.product.id, "quantity": 1, "price_unit": 200.0,
                "tax_ids": [(6, 0, [])],
            })],
        })
        if post:
            move.action_post()
        return move

    def _issue(self, move, user=None):
        move = move.with_user(user or self.cashier)
        move.action_mira_siat_issue()
        return self.env["mira.siat.invoice"].search(
            [("move_id", "=", move.id)], order="id desc", limit=1)
