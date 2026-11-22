from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("mirabilenet", "post_install", "-at_install")
class TestMirabilenetClientesPlanes(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Region = cls.env["mirabilenet.region"]
        cls.norte = Region.create({"code": "T-N", "name": "Norte", "wg_region_id": 1})
        cls.sur = Region.create({"code": "T-S", "name": "Sur", "wg_region_id": 2})
        Zone = cls.env["mirabilenet.zone"]
        cls.zone_n = Zone.create({"region_id": cls.norte.id, "code": "T-N-Z", "name": "ZN"})
        cls.zone_s = Zone.create({"region_id": cls.sur.id, "code": "T-S-Z", "name": "ZS"})

        cls.gerencia = cls._user("t_gerencia", "gerencia")
        cls.auditor = cls._user("t_auditor", "auditor")
        cls.admin_n = cls._user("t_admin_n", "admin_regional", cls.norte)
        cls.vendedor_n = cls._user("t_vendedor_n", "vendedor", cls.norte)
        cls.tecnico_n = cls._user("t_tecnico_n", "tecnico", cls.norte)
        cls.pasante = cls._user("t_pasante", "pasante", cls.norte)

        Partner = cls.env["res.partner"]
        cls.cliente_n = Partner.create({
            "name": "Cliente Norte", "mirabilenet_is_customer": True,
            "mirabilenet_region_id": cls.norte.id})
        cls.cliente_s = Partner.create({
            "name": "Cliente Sur", "mirabilenet_is_customer": True,
            "mirabilenet_region_id": cls.sur.id})
        cls.contacto_s = Partner.create({"name": "Contacto Sur", "parent_id": cls.cliente_s.id})
        cls.proveedor = Partner.create({"name": "Proveedor cualquiera"})

        Plan = cls.env["product.template"]
        cls.plan_global = Plan.create(cls._plan_vals("T-GLOBAL", None, 100))
        cls.plan_n = Plan.create(cls._plan_vals("T-NORTE", cls.norte, 200))
        cls.plan_s = Plan.create(cls._plan_vals("T-SUR", cls.sur, 300))

    @classmethod
    def _user(cls, login, role, region=None):
        user = new_test_user(cls.env, login, groups="base.group_user")
        user.write({"mirabilenet_role": role,
                    "mirabilenet_region_id": region.id if region else False})
        return user

    @classmethod
    def _plan_vals(cls, code, region, price):
        return {"name": code, "type": "service", "mirabilenet_is_plan": True,
                "mirabilenet_plan_code": code, "list_price": price,
                "mirabilenet_region_id": region.id if region else False,
                "mirabilenet_down_mbps": 20, "mirabilenet_up_mbps": 10}

    # -- Clientes: aislamiento -----------------------------------------
    def test_customers_are_isolated_by_region(self):
        Partner = self.env["res.partner"].with_user(self.tecnico_n)
        found = Partner.search([("mirabilenet_is_customer", "=", True)])
        self.assertIn(self.cliente_n, found)
        self.assertNotIn(self.cliente_s, found)
        for other in (self.cliente_s, self.contacto_s):
            with self.assertRaises(AccessError):
                Partner.browse(other.id).read(["name"])
        # Lo que no es cliente se sigue viendo.
        self.assertTrue(Partner.browse(self.proveedor.id).read(["name"]))

    def test_global_roles_see_all_customers(self):
        for user in (self.gerencia, self.auditor):
            found = self.env["res.partner"].with_user(user).search(
                [("mirabilenet_is_customer", "=", True)])
            self.assertIn(self.cliente_n, found)
            self.assertIn(self.cliente_s, found)

    def test_pasante_sees_no_customers(self):
        Partner = self.env["res.partner"].with_user(self.pasante)
        self.assertFalse(Partner.search([("mirabilenet_is_customer", "=", True)]))
        with self.assertRaises(AccessError):
            Partner.browse(self.cliente_n.id).read(["name"])
        self.assertTrue(Partner.browse(self.proveedor.id).read(["name"]))

    def test_contacts_follow_their_customer(self):
        self.assertTrue(self.contacto_s.mirabilenet_restricted)
        self.assertEqual(self.contacto_s.mirabilenet_scope_region_id, self.sur)
        self.assertFalse(self.proveedor.mirabilenet_restricted)

    # -- Clientes: alta y edición --------------------------------------
    def test_seller_creates_customers_only_in_own_region(self):
        Partner = self.env["res.partner"].with_user(self.vendedor_n)
        nuevo = Partner.create({"name": "Nuevo", "mirabilenet_is_customer": True,
                                "mirabilenet_region_id": self.norte.id,
                                "mirabilenet_zone_id": self.zone_n.id})
        self.assertTrue(nuevo.mirabilenet_code.startswith("CLI-"))
        self.assertEqual(nuevo.mirabilenet_state, "prospecto")
        with self.assertRaises(AccessError):
            Partner.create({"name": "Ajeno", "mirabilenet_is_customer": True,
                            "mirabilenet_region_id": self.sur.id})
        with self.assertRaises(AccessError):
            nuevo.write({"mirabilenet_region_id": self.sur.id, "mirabilenet_zone_id": False})

    def test_codes_are_unique_and_automatic(self):
        self.assertTrue(self.cliente_n.mirabilenet_code)
        self.assertNotEqual(self.cliente_n.mirabilenet_code, self.cliente_s.mirabilenet_code)
        self.proveedor.write({"mirabilenet_is_customer": True,
                              "mirabilenet_region_id": self.norte.id})
        self.assertTrue(self.proveedor.mirabilenet_code)

    def test_customer_needs_region_and_matching_zone(self):
        with self.assertRaises(ValidationError):
            self.env["res.partner"].create({"name": "Sin región",
                                            "mirabilenet_is_customer": True})
        with self.assertRaises(ValidationError):
            self.cliente_n.write({"mirabilenet_zone_id": self.zone_s.id})

    def test_roles_that_cannot_edit_customers(self):
        for user in (self.tecnico_n, self.auditor):
            with self.assertRaises(AccessError):
                self.cliente_n.with_user(user).write({"phone": "70000000"})
            with self.assertRaises(AccessError):
                self.env["res.partner"].with_user(user).create(
                    {"name": "X", "mirabilenet_is_customer": True,
                     "mirabilenet_region_id": self.norte.id})

    def test_technician_maintains_contacts_but_not_customers(self):
        Partner = self.env["res.partner"].with_user(self.tecnico_n)
        contact = Partner.create({"name": "Encargado", "parent_id": self.cliente_n.id,
                                  "phone": "70000009"})
        contact.write({"mirabilenet_authorized_payments": True})
        self.assertTrue(contact.mirabilenet_restricted)
        with self.assertRaises(AccessError):
            self.cliente_n.with_user(self.tecnico_n).write({"phone": "70000000"})
        with self.assertRaises(AccessError):
            Partner.create({"name": "Ajeno", "parent_id": self.cliente_s.id})
        with self.assertRaises(AccessError):
            contact.write({"parent_id": self.proveedor.id})
        with self.assertRaises(AccessError):
            contact.write({"mirabilenet_is_customer": True,
                           "mirabilenet_region_id": self.norte.id})
        with self.assertRaises(AccessError):
            self.env["res.partner"].with_user(self.pasante).create(
                {"name": "X", "parent_id": self.cliente_n.id})

    # -- Clientes: estado comercial ------------------------------------
    def test_state_changes_only_through_the_action(self):
        cliente = self.cliente_n.with_user(self.vendedor_n)
        with self.assertRaises(UserError):
            cliente.write({"mirabilenet_state": "activo"})
        for target in ("evaluacion", "cotizado", "instalacion_pendiente", "activo"):
            cliente.action_mirabilenet_set_state(target)
        self.assertEqual(self.cliente_n.mirabilenet_state, "activo")

    def test_invalid_transitions_are_rejected(self):
        cliente = self.cliente_n.with_user(self.vendedor_n)
        with self.assertRaises(UserError):
            cliente.action_mirabilenet_set_state("activo")
        cliente.action_mirabilenet_set_state("cancelado")
        with self.assertRaises(UserError):
            cliente.action_mirabilenet_set_state("prospecto")
        with self.assertRaises(UserError):
            cliente.action_mirabilenet_set_state("inventado")

    def test_new_customer_cannot_be_born_active(self):
        with self.assertRaises(UserError):
            self.env["res.partner"].with_user(self.vendedor_n).create(
                {"name": "Atajo", "mirabilenet_is_customer": True,
                 "mirabilenet_region_id": self.norte.id, "mirabilenet_state": "activo"})

    def test_state_action_respects_role_and_region(self):
        with self.assertRaises(AccessError):
            self.cliente_n.with_user(self.tecnico_n).action_mirabilenet_set_state("evaluacion")
        with self.assertRaises(AccessError):
            self.cliente_s.with_user(self.vendedor_n).action_mirabilenet_set_state("evaluacion")

    # -- Planes ---------------------------------------------------------
    def test_plan_publication_rule(self):
        plan = self.plan_n
        self.assertFalse(plan.mirabilenet_publish_web, "«Publicar» nace apagado")
        self.assertFalse(plan.mirabilenet_published)
        plan.mirabilenet_publish_web = True
        self.assertTrue(plan.mirabilenet_published)
        plan.list_price = 0
        self.assertFalse(plan.mirabilenet_published, "sin precio no se publica")
        plan.list_price = 200
        plan.active = False
        self.assertFalse(plan.mirabilenet_published, "inactivo no se publica")
        plan.active = True
        published = self.env["product.template"].search([("mirabilenet_published", "=", True)])
        self.assertIn(plan, published)
        self.assertNotIn(self.plan_s, published)

    def test_plans_visible_by_region(self):
        found = self.env["product.template"].with_user(self.tecnico_n).search(
            [("mirabilenet_is_plan", "=", True)])
        self.assertIn(self.plan_global, found)
        self.assertIn(self.plan_n, found)
        self.assertNotIn(self.plan_s, found)
        with self.assertRaises(AccessError):
            self.plan_s.with_user(self.tecnico_n).read(["name"])
        with self.assertRaises(AccessError):
            self.plan_s.product_variant_id.with_user(self.tecnico_n).read(["name"])
        self.assertIn(self.plan_s, self.env["product.template"].with_user(self.gerencia).search(
            [("mirabilenet_is_plan", "=", True)]))

    def test_only_management_edits_plans(self):
        for user in (self.vendedor_n, self.tecnico_n, self.auditor, self.pasante):
            with self.assertRaises(AccessError, msg=user.login):
                self.plan_n.with_user(user).write({"list_price": 1})
            with self.assertRaises(AccessError, msg=user.login):
                self.env["product.template"].with_user(user).create(
                    self._plan_vals("T-X-%s" % user.id, self.norte, 10))
        self.plan_n.with_user(self.admin_n).write({"list_price": 210})
        self.assertEqual(self.plan_n.list_price, 210)
        self.env["product.template"].with_user(self.admin_n).create(
            self._plan_vals("T-NORTE-2", self.norte, 90))

    def test_regional_admin_cannot_reach_other_region_plans(self):
        with self.assertRaises(AccessError):
            self.plan_s.with_user(self.admin_n).write({"list_price": 1})
        with self.assertRaises(AccessError):
            self.env["product.template"].with_user(self.admin_n).create(
                self._plan_vals("T-SUR-2", self.sur, 90))
        with self.assertRaises(AccessError):
            self.plan_n.with_user(self.admin_n).write({"mirabilenet_region_id": self.sur.id})

    def test_plan_deletion_rules(self):
        with self.assertRaises(AccessError):
            self.plan_global.with_user(self.admin_n).unlink()
        plan_id = self.plan_n.id
        self.plan_n.with_user(self.admin_n).unlink()
        entry = self.env["mirabilenet.audit.log"].search(
            [("action", "=", "eliminar"), ("res_id", "=", plan_id)], limit=1)
        self.assertEqual(entry.user_id, self.admin_n)
        self.plan_global.with_user(self.gerencia).unlink()

    def test_plan_constraints(self):
        with self.assertRaises(ValidationError):
            self.plan_s.mirabilenet_down_mbps = 0
        self.assertEqual(self.plan_s.mirabilenet_profile_name, "T-SUR")
        self.plan_s.mirabilenet_ppp_profile = "perfil-sur"
        self.assertEqual(self.plan_s.mirabilenet_profile_name, "perfil-sur")
