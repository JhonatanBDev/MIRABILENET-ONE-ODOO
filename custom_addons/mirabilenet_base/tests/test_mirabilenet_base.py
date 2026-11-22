from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged("mirabilenet", "post_install", "-at_install")
class TestMirabilenetBase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Region = cls.env["mirabilenet.region"]
        cls.norte = Region.create({"code": "T-N", "name": "Norte", "wg_region_id": 1})
        cls.sur = Region.create({"code": "T-S", "name": "Sur", "wg_region_id": 2})
        Branch = cls.env["mirabilenet.branch"]
        cls.branch_n = Branch.create({"region_id": cls.norte.id, "code": "T-N-1", "name": "BN"})
        cls.branch_s = Branch.create({"region_id": cls.sur.id, "code": "T-S-1", "name": "BS"})
        Zone = cls.env["mirabilenet.zone"]
        cls.zone_n = Zone.create({"region_id": cls.norte.id, "code": "T-N-Z", "name": "ZN"})
        cls.zone_s = Zone.create({"region_id": cls.sur.id, "code": "T-S-Z", "name": "ZS"})
        Node = cls.env["mirabilenet.node"]
        cls.node_n = Node.create({"zone_id": cls.zone_n.id, "code": "T-N-N", "name": "NN"})
        cls.node_s = Node.create({"zone_id": cls.zone_s.id, "code": "T-S-N", "name": "NS"})

        cls.superadmin = cls._user("t_super", "superadmin")
        cls.gerencia = cls._user("t_gerencia", "gerencia")
        cls.auditor = cls._user("t_auditor", "auditor")
        cls.admin_n = cls._user("t_admin_n", "admin_regional", cls.norte)
        cls.admin_s = cls._user("t_admin_s", "admin_regional", cls.sur)
        cls.tecnico_n = cls._user("t_tecnico_n", "tecnico", cls.norte)
        cls.tecnico_s = cls._user("t_tecnico_s", "tecnico", cls.sur)
        cls.pasante = cls._user("t_pasante", "pasante", cls.norte)

    @classmethod
    def _user(cls, login, role, region=None):
        user = new_test_user(cls.env, login, groups="base.group_user")
        user.write({"mirabilenet_role": role,
                    "mirabilenet_region_id": region.id if region else False})
        return user

    def _group(self, role):
        return self.env.ref("mirabilenet_base.group_role_%s" % role)

    # -- Organización ---------------------------------------------------
    def test_region_blocks(self):
        self.assertEqual(self.norte.bloque_gestion, "10.250.10.0/24")
        self.assertEqual(self.norte.bloque_camaras, "10.65.0.0/16")
        self.assertEqual(self.node_n.region_id, self.norte)

    def test_region_constraints(self):
        with self.assertRaises(ValidationError):
            self.norte.dia_emision = 32
        with self.assertRaises(ValidationError):
            self.norte.hora_corte = 24.0
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.env["mirabilenet.region"].create(
                    {"code": "T-X", "name": "X", "wg_region_id": 64})
        with self.assertRaises(UserError):
            self.sur.unlink()

    # -- Aislamiento por región ----------------------------------------
    def test_regional_user_sees_only_own_region(self):
        for model, own, other in (
            ("mirabilenet.region", self.norte, self.sur),
            ("mirabilenet.branch", self.branch_n, self.branch_s),
            ("mirabilenet.zone", self.zone_n, self.zone_s),
            ("mirabilenet.node", self.node_n, self.node_s),
        ):
            records = self.env[model].with_user(self.tecnico_n)
            found = records.search([])
            self.assertIn(own, found, model)
            self.assertNotIn(other, found, model)
            # Pedirlo por id tampoco funciona.
            with self.assertRaises(AccessError, msg=model):
                records.browse(other.id).read(["display_name"])

    def test_regional_manager_cannot_write_other_region(self):
        zones = self.env["mirabilenet.zone"].with_user(self.admin_n)
        zones.browse(self.zone_n.id).write({"sector": "Centro"})
        zones.create({"region_id": self.norte.id, "code": "T-N-Z2", "name": "ZN2"})
        with self.assertRaises(AccessError):
            zones.browse(self.zone_s.id).write({"sector": "Ajeno"})
        with self.assertRaises(AccessError):
            zones.create({"region_id": self.sur.id, "code": "T-S-Z2", "name": "ZS2"})
        with self.assertRaises(AccessError):
            zones.browse(self.zone_n.id).write({"region_id": self.sur.id})
        with self.assertRaises(AccessError):
            self.env["mirabilenet.node"].with_user(self.admin_n).create(
                {"zone_id": self.zone_s.id, "code": "T-S-N2", "name": "NS2"})

    def test_plain_role_cannot_write(self):
        with self.assertRaises(AccessError):
            self.zone_n.with_user(self.tecnico_n).write({"sector": "x"})
        # El calendario de cobro de la región no lo toca el administrador regional.
        with self.assertRaises(AccessError):
            self.norte.with_user(self.admin_n).write({"dias_gracia": 9})

    def test_global_roles_see_everything(self):
        for user in (self.superadmin, self.gerencia, self.auditor):
            found = self.env["mirabilenet.zone"].with_user(user).search([])
            self.assertIn(self.zone_n, found)
            self.assertIn(self.zone_s, found)
        self.norte.with_user(self.gerencia).write({"dias_gracia": 5})
        self.assertEqual(self.norte.dias_gracia, 5)

    def test_auditor_reads_but_never_writes(self):
        self.assertTrue(self.norte.with_user(self.auditor).read(["name"]))
        for record in (self.norte, self.branch_n, self.zone_n, self.node_n):
            with self.assertRaises(AccessError):
                record.with_user(self.auditor).write({"name": "cambiado"})
        with self.assertRaises(AccessError):
            self.env["mirabilenet.zone"].with_user(self.auditor).create(
                {"region_id": self.norte.id, "code": "T-A", "name": "A"})

    def test_pasante_sees_nothing_of_the_organization(self):
        for model in ("mirabilenet.region", "mirabilenet.branch", "mirabilenet.zone",
                      "mirabilenet.node", "mirabilenet.audit.log"):
            with self.assertRaises(AccessError, msg=model):
                self.env[model].with_user(self.pasante).search([])
        self.assertFalse(self.pasante.has_group("mirabilenet_base.group_mirabilenet_user"))

    def test_user_without_region_sees_nothing(self):
        orphan = self._user("t_sin_region", "tecnico")
        self.assertFalse(self.env["mirabilenet.zone"].with_user(orphan).search([]))
        self.assertFalse(self.env["mirabilenet.region"].with_user(orphan).search([]))

    # -- Rol y grupos ---------------------------------------------------
    def test_role_sets_exactly_one_role_group(self):
        user = self.tecnico_n
        self.assertIn(self._group("tecnico"), user.group_ids)
        user.write({"mirabilenet_role": "cajero"})
        self.assertIn(self._group("cajero"), user.group_ids)
        self.assertNotIn(self._group("tecnico"), user.group_ids)
        user.write({"mirabilenet_role": False})
        self.assertFalse(user.has_group("mirabilenet_base.group_mirabilenet_user"))

    def test_branch_must_belong_to_region(self):
        with self.assertRaises(ValidationError):
            self.tecnico_n.write({"mirabilenet_branch_id": self.branch_s.id})

    # -- Administración de usuarios ------------------------------------
    def _new_vals(self, login, role, region):
        return {"name": login, "login": login, "mirabilenet_role": role,
                "mirabilenet_region_id": region.id if region else False}

    def test_regional_admin_creates_only_in_own_region(self):
        Users = self.env["res.users"].with_user(self.admin_n)
        user = Users.mirabilenet_create_user(self._new_vals("t_nuevo", "cajero", self.norte))
        self.assertEqual(user.mirabilenet_region_id, self.norte)
        self.assertIn(self._group("cajero"), user.group_ids)
        with self.assertRaises(AccessError):
            Users.mirabilenet_create_user(self._new_vals("t_ajeno", "cajero", self.sur))
        with self.assertRaises(AccessError):
            Users.mirabilenet_create_user(self._new_vals("t_global", "cajero", None))

    def test_nobody_grants_a_role_above_their_own(self):
        for actor in (self.admin_n, self.gerencia):
            Users = self.env["res.users"].with_user(actor)
            for role in ("superadmin", "gerencia", "auditor"):
                with self.assertRaises(AccessError, msg="%s -> %s" % (actor.login, role)):
                    Users.mirabilenet_create_user(
                        self._new_vals("t_%s_%s" % (actor.id, role), role, self.norte))
            with self.assertRaises(AccessError):
                self.tecnico_n.with_user(actor).mirabilenet_update_user(
                    {"mirabilenet_role": "gerencia"})
        created = self.env["res.users"].with_user(self.superadmin).mirabilenet_create_user(
            self._new_vals("t_ger2", "gerencia", None))
        self.assertTrue(created.mirabilenet_is_global)

    def test_non_super_cannot_touch_global_users(self):
        with self.assertRaises(AccessError):
            self.auditor.with_user(self.gerencia).mirabilenet_update_user({"active": False})
        with self.assertRaises(AccessError):
            self.superadmin.with_user(self.gerencia).mirabilenet_update_user(
                {"mirabilenet_role": "tecnico"})

    def test_regional_admin_cannot_touch_other_region_users(self):
        with self.assertRaises(AccessError):
            self.tecnico_s.with_user(self.admin_n).mirabilenet_update_user({"active": False})
        with self.assertRaises(AccessError):
            self.tecnico_n.with_user(self.admin_n).mirabilenet_update_user(
                {"mirabilenet_region_id": self.sur.id})
        self.tecnico_n.with_user(self.admin_n).mirabilenet_update_user({"active": False})
        self.assertFalse(self.tecnico_n.active)

    def test_nobody_edits_themselves(self):
        for actor in (self.superadmin, self.gerencia, self.admin_n):
            with self.assertRaises(UserError):
                actor.with_user(actor).mirabilenet_update_user({"mirabilenet_role": "noc"})
            with self.assertRaises(UserError):
                actor.with_user(actor).mirabilenet_update_user({"active": False})

    def test_roles_without_user_admin_are_rejected(self):
        for actor in (self.tecnico_n, self.auditor, self.pasante):
            with self.assertRaises(AccessError):
                self.env["res.users"].with_user(actor).mirabilenet_create_user(
                    self._new_vals("t_x_%s" % actor.id, "cajero", self.norte))
            with self.assertRaises(AccessError):
                self.tecnico_s.with_user(actor).mirabilenet_update_user({"active": False})

    def test_groups_cannot_be_injected(self):
        system = self.env.ref("base.group_system")
        with self.assertRaises(AccessError):
            self.tecnico_n.with_user(self.gerencia).mirabilenet_update_user(
                {"group_ids": [(4, system.id)]})
        vals = self._new_vals("t_inyecta", "cajero", self.norte)
        vals["group_ids"] = [(4, system.id)]
        with self.assertRaises(AccessError):
            self.env["res.users"].with_user(self.gerencia).mirabilenet_create_user(vals)

    def test_users_are_deactivated_not_deleted(self):
        with self.assertRaises(UserError):
            self.tecnico_n.unlink()

    # -- Auditoría ------------------------------------------------------
    def test_permission_changes_are_audited(self):
        Log = self.env["mirabilenet.audit.log"]
        self.tecnico_n.with_user(self.admin_n).mirabilenet_update_user(
            {"mirabilenet_role": "cobrador"})
        entry = Log.search([("model", "=", "res.users"), ("res_id", "=", self.tecnico_n.id)],
                           limit=1)
        self.assertEqual(entry.user_id, self.admin_n)
        self.assertEqual(entry.region_id, self.norte)
        self.assertEqual(entry.payload["mirabilenet_role"], ["tecnico", "cobrador"])
        with self.assertRaises(UserError):
            entry.write({"description": "otro"})
        with self.assertRaises(UserError):
            entry.unlink()

    def test_audit_log_is_isolated_by_region(self):
        self.tecnico_s.with_user(self.admin_s).mirabilenet_update_user({"active": False})
        Log = self.env["mirabilenet.audit.log"]
        domain = [("res_id", "=", self.tecnico_s.id), ("model", "=", "res.users")]
        self.assertTrue(Log.with_user(self.admin_s).search(domain))
        self.assertFalse(Log.with_user(self.admin_n).search(domain))
        self.assertTrue(Log.with_user(self.auditor).search(domain))

    def test_users_screen_is_scoped(self):
        action = self.env["res.users"].with_user(self.admin_n).action_mirabilenet_users()
        users = self.env["res.users"].with_context(active_test=False).search(action["domain"])
        self.assertIn(self.tecnico_n, users)
        self.assertNotIn(self.tecnico_s, users)
        action = self.env["res.users"].with_user(self.gerencia).action_mirabilenet_users()
        users = self.env["res.users"].with_context(active_test=False).search(action["domain"])
        self.assertIn(self.tecnico_s, users)

    def test_wizard_saves_through_the_same_barriers(self):
        Wizard = self.env["mirabilenet.user.wizard"].with_user(self.admin_n)
        wizard = Wizard.create({"name": "Ana", "login": "t_ana", "role": "vendedor",
                                "region_id": self.norte.id})
        wizard.action_save()
        ana = self.env["res.users"].search([("login", "=", "t_ana")])
        self.assertEqual(ana.mirabilenet_role, "vendedor")
        edit = Wizard.with_context(default_user_id=self.tecnico_s.id).create(
            {"name": "x", "login": "t_tecnico_s", "role": "cajero", "region_id": self.sur.id})
        with self.assertRaises(AccessError):
            edit.action_save()
