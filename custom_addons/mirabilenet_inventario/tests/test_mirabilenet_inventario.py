from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("mirabilenet", "post_install", "-at_install")
class TestMirabilenetInventario(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Region = cls.env["mirabilenet.region"]
        cls.norte = Region.create({"code": "T-N", "name": "Norte", "wg_region_id": 1})
        cls.sur = Region.create({"code": "T-S", "name": "Sur", "wg_region_id": 2})
        Branch = cls.env["mirabilenet.branch"]
        branch_n = Branch.create({"region_id": cls.norte.id, "code": "TN1", "name": "BN"})
        branch_s = Branch.create({"region_id": cls.sur.id, "code": "TS1", "name": "BS"})
        Warehouse = cls.env["stock.warehouse"]
        cls.wh_n = Warehouse.create({"name": "Almacén Norte", "code": "TALN",
                                     "mirabilenet_branch_id": branch_n.id})
        cls.wh_n2 = Warehouse.create({"name": "Almacén Norte 2", "code": "TAN2",
                                      "mirabilenet_branch_id": branch_n.id})
        cls.wh_s = Warehouse.create({"name": "Almacén Sur", "code": "TALS",
                                     "mirabilenet_branch_id": branch_s.id})

        cls.gerencia = cls._user("t_gerencia", "gerencia")
        cls.auditor = cls._user("t_auditor", "auditor")
        cls.almacen_n = cls._user("t_almacen_n", "almacenista", cls.norte)
        cls.almacen_s = cls._user("t_almacen_s", "almacenista", cls.sur)
        cls.tecnico_n = cls._user("t_tecnico_n", "tecnico", cls.norte)
        cls.cajero_n = cls._user("t_cajero_n", "cajero", cls.norte)
        cls.pasante = cls._user("t_pasante", "pasante", cls.norte)

        Partner = cls.env["res.partner"]
        cls.cliente_n = Partner.create({"name": "Cliente Norte", "mirabilenet_is_customer": True,
                                        "mirabilenet_region_id": cls.norte.id})
        cls.cliente_s = Partner.create({"name": "Cliente Sur", "mirabilenet_is_customer": True,
                                        "mirabilenet_region_id": cls.sur.id})
        Product = cls.env["product.product"]
        cls.onu = Product.create({"name": "ONU de prueba", "default_code": "T-ONU",
                                  "type": "consu", "is_storable": True, "tracking": "serial",
                                  "categ_id": cls.env.ref(
                                      "mirabilenet_inventario.category_onu").id})
        cls.fibra = Product.create({"name": "Fibra drop", "default_code": "T-FIBRA",
                                    "type": "consu", "is_storable": True, "tracking": "none",
                                    "mirabilenet_stock_min": 100})
        cls.servicio = Product.create({"name": "Mano de obra", "type": "service"})

    @classmethod
    def _user(cls, login, role, region=None):
        user = new_test_user(cls.env, login, groups="base.group_user")
        user.write({"mirabilenet_role": role,
                    "mirabilenet_region_id": region.id if region else False})
        return user

    def _move(self, kind, product, user=None, **kwargs):
        return self.env["stock.move"].with_user(user or self.almacen_n)._mirabilenet_move(
            kind, product, **kwargs)

    def _buy_serial(self, name="SN-001", warehouse=None, user=None):
        move = self._move("compra", self.onu, user=user, lot_name=name,
                          dest=warehouse or self.wh_n)
        return move.mirabilenet_lot_id

    def _qty(self, product, warehouse):
        return self.env["stock.quant"]._get_available_quantity(
            product, warehouse.lot_stock_id)

    # -- Serializados ---------------------------------------------------
    def test_serial_life_cycle(self):
        lot = self._buy_serial()
        self.assertEqual((lot.mirabilenet_state, lot.mirabilenet_warehouse_id,
                          lot.mirabilenet_region_id),
                         ("en_almacen", self.wh_n, self.norte))
        self.assertEqual(self._qty(self.onu, self.wh_n), 1)

        self._move("salida_tecnico", self.onu, lot=lot, technician=self.tecnico_n)
        self.assertEqual((lot.mirabilenet_state, lot.mirabilenet_technician_id),
                         ("con_tecnico", self.tecnico_n))
        self.assertEqual(self._qty(self.onu, self.wh_n), 0, "ya no está en el depósito")

        self._move("asignacion_cliente", self.onu, user=self.tecnico_n, lot=lot,
                   partner=self.cliente_n)
        self.assertEqual((lot.mirabilenet_state, lot.mirabilenet_partner_id),
                         ("en_cliente", self.cliente_n))
        self.assertFalse(lot.mirabilenet_technician_id)
        self.assertIn(lot, self.cliente_n.mirabilenet_equipment_ids)

        self._move("devolucion", self.onu, lot=lot, dest=self.wh_n2)
        self.assertEqual((lot.mirabilenet_state, lot.mirabilenet_warehouse_id),
                         ("en_almacen", self.wh_n2))
        self.assertFalse(lot.mirabilenet_partner_id)
        self.assertEqual(self._qty(self.onu, self.wh_n2), 1)

        self._move("reparacion", self.onu, lot=lot)
        self.assertEqual(lot.mirabilenet_state, "en_reparacion")
        self._move("devolucion", self.onu, lot=lot, dest=self.wh_n)
        self._move("transferencia", self.onu, lot=lot, source=self.wh_n, dest=self.wh_n2)
        self.assertEqual((lot.mirabilenet_state, lot.mirabilenet_warehouse_id),
                         ("en_almacen", self.wh_n2))
        self._move("baja", self.onu, lot=lot, reason="Quemado por descarga")
        self.assertEqual(lot.mirabilenet_state, "baja")
        self.assertEqual(self._qty(self.onu, self.wh_n2), 0)
        with self.assertRaises(UserError):
            self._move("devolucion", self.onu, lot=lot, dest=self.wh_n)

    def test_serial_rules(self):
        with self.assertRaises(UserError):
            self._move("compra", self.onu, dest=self.wh_n)  # falta la serie
        lot = self._buy_serial()
        with self.assertRaises(UserError):
            self._buy_serial()  # serie repetida
        with self.assertRaises(UserError):
            self._move("salida_tecnico", self.onu, lot=lot)  # falta el técnico
        with self.assertRaises(UserError):
            self._move("salida_tecnico", self.onu, technician=self.tecnico_n)  # falta la serie
        with self.assertRaises(UserError):
            self._move("asignacion_cliente", self.onu, lot=lot)  # falta el cliente
        with self.assertRaises(UserError):
            self._move("asignacion_cliente", self.onu, lot=lot, partner=self.cliente_s)
        with self.assertRaises(UserError):
            self._move("ajuste", self.onu, lot=lot, dest=self.wh_n)
        with self.assertRaises(UserError):
            self._move("transferencia", self.onu, lot=lot, source=self.wh_n2, dest=self.wh_n)
        with self.assertRaises(UserError):
            self._move("devolucion", self.onu, lot=lot, dest=self.wh_n)  # ya está ahí
        with self.assertRaises(UserError):
            self._move("compra", self.servicio, dest=self.wh_n)

    def test_serial_situation_is_not_editable(self):
        lot = self._buy_serial()
        with self.assertRaises(UserError):
            lot.with_user(self.almacen_n).write({"mirabilenet_state": "baja"})
        with self.assertRaises(UserError):
            lot.with_user(self.almacen_n).with_context(mirabilenet_inventory=True).write(
                {"mirabilenet_partner_id": self.cliente_n.id})
        lot.with_user(self.tecnico_n).write({"mirabilenet_mac": "AA:BB:CC:00:11:22"})
        self.assertEqual(lot.mirabilenet_mac, "AA:BB:CC:00:11:22")

    # -- A granel -------------------------------------------------------
    def test_bulk_stock(self):
        self._move("compra", self.fibra, quantity=500, dest=self.wh_n)
        self.assertEqual(self._qty(self.fibra, self.wh_n), 500)
        self._move("transferencia", self.fibra, quantity=200, source=self.wh_n,
                   dest=self.wh_n2)
        self._move("consumo", self.fibra, user=self.tecnico_n, quantity=120,
                   source=self.wh_n, partner=self.cliente_n)
        self.assertEqual(self._qty(self.fibra, self.wh_n), 180)
        self.assertEqual(self._qty(self.fibra, self.wh_n2), 200)
        with self.assertRaises(UserError):
            self._move("consumo", self.fibra, quantity=181, source=self.wh_n)
        with self.assertRaises(UserError):
            self._move("transferencia", self.fibra, quantity=1, source=self.wh_n,
                       dest=self.wh_n)
        with self.assertRaises(UserError):
            self._move("consumo", self.fibra, quantity=0, source=self.wh_n)
        with self.assertRaises(UserError):
            self._move("salida_tecnico", self.fibra, quantity=1, source=self.wh_n,
                       technician=self.tecnico_n)
        self.assertEqual(self._qty(self.fibra, self.wh_n), 180, "un rechazo no mueve nada")

    def test_adjustment(self):
        self._move("ajuste", self.fibra, quantity=50, dest=self.wh_n, reason="Conteo")
        self.assertEqual(self._qty(self.fibra, self.wh_n), 50)
        self._move("ajuste", self.fibra, quantity=20, source=self.wh_n, reason="Conteo")
        self.assertEqual(self._qty(self.fibra, self.wh_n), 30)
        with self.assertRaises(UserError):
            self._move("ajuste", self.fibra, quantity=1, source=self.wh_n, dest=self.wh_n2)

    def test_below_minimum(self):
        template = self.fibra.product_tmpl_id
        self.assertTrue(template.mirabilenet_below_min)
        self._move("compra", self.fibra, quantity=100, dest=self.wh_n)
        template.invalidate_recordset()
        self.assertFalse(template.mirabilenet_below_min)
        self.assertNotIn(template, self.env["product.template"].search(
            [("mirabilenet_below_min", "=", True)]))

    # -- Rastro ---------------------------------------------------------
    def test_movements_leave_a_trail_and_cannot_be_altered(self):
        move = self._move("compra", self.fibra, quantity=10, dest=self.wh_n,
                          document="FAC-123", reason="Reposición")
        self.assertEqual((move.state, move.mirabilenet_kind, move.mirabilenet_region_id,
                          move.mirabilenet_user_id, move.mirabilenet_document),
                         ("done", "compra", self.norte, self.almacen_n, "FAC-123"))
        log = self.env["mirabilenet.audit.log"].search(
            [("action", "=", "inventario_mover"), ("res_id", "=", move.id)], limit=1)
        self.assertEqual((log.user_id, log.region_id), (self.almacen_n, self.norte))
        with self.assertRaises(UserError):
            move.with_user(self.almacen_n).write({"mirabilenet_reason": "otro"})
        with self.assertRaises(UserError):
            move.with_user(self.almacen_n).unlink()

    # -- Roles y regiones ----------------------------------------------
    def test_who_can_move(self):
        for user in (self.cajero_n, self.auditor, self.pasante, self.gerencia):
            with self.assertRaises(AccessError, msg=user.login):
                self._move("compra", self.fibra, user=user, quantity=1, dest=self.wh_n)
        with self.assertRaises(AccessError):
            self._move("compra", self.fibra, user=self.almacen_s, quantity=1, dest=self.wh_n)
        self._move("compra", self.fibra, quantity=10, dest=self.wh_n)
        with self.assertRaises(AccessError):
            self._move("transferencia", self.fibra, quantity=1, source=self.wh_n,
                       dest=self.wh_s)

    def test_inventory_is_isolated_by_region(self):
        lot_n = self._buy_serial("SN-N")
        lot_s = self._buy_serial("SN-S", warehouse=self.wh_s, user=self.almacen_s)
        env_n = self.env(user=self.almacen_n)
        self.assertNotIn(self.wh_s, env_n["stock.warehouse"].search([]))
        self.assertIn(self.wh_n, env_n["stock.warehouse"].search([]))
        lots = env_n["stock.lot"].search([("product_id", "=", self.onu.id)])
        self.assertEqual(lots, lot_n)
        with self.assertRaises(AccessError):
            lot_s.with_user(self.almacen_n).read(["name"])
        quants = env_n["stock.quant"].search([("product_id", "=", self.onu.id),
                                              ("location_id.usage", "=", "internal")])
        self.assertEqual(quants.mapped("lot_id"), lot_n)
        moves = env_n["stock.move"].search([("mirabilenet_kind", "!=", False)])
        self.assertEqual(moves.mapped("mirabilenet_region_id"), self.norte)
        with self.assertRaises(AccessError):
            self._move("devolucion", self.onu, lot=lot_s, dest=self.wh_n)
        with self.assertRaises(AccessError):
            self.wh_n.with_user(self.almacen_n).write(
                {"mirabilenet_branch_id": self.wh_s.mirabilenet_branch_id.id})

    def test_auditor_reads_everything_and_writes_nothing(self):
        lot = self._buy_serial()
        env_a = self.env(user=self.auditor)
        self.assertIn(lot, env_a["stock.lot"].search([("product_id", "=", self.onu.id)]))
        self.assertTrue(env_a["stock.move"].search([("mirabilenet_lot_id", "=", lot.id)]))
        with self.assertRaises(AccessError):
            lot.with_user(self.auditor).write({"mirabilenet_mac": "x"})
        with self.assertRaises(AccessError):
            self.wh_n.with_user(self.auditor).write({"name": "x"})

    def test_pasante_sees_no_inventory(self):
        self._buy_serial()
        env_p = self.env(user=self.pasante)
        with self.assertRaises(AccessError):
            env_p["stock.lot"].search([])
        with self.assertRaises(AccessError):
            env_p["stock.move"].search([])
        self.assertFalse(env_p["stock.quant"].search(
            [("product_id", "=", self.onu.id), ("location_id.usage", "=", "internal")]))

    def test_manager_creates_warehouses_only_in_own_region(self):
        branch_n = self.wh_n.mirabilenet_branch_id
        Warehouse = self.env["stock.warehouse"].with_user(self.almacen_n)
        new = Warehouse.create({"name": "Depósito 3", "code": "TDP3",
                                "mirabilenet_branch_id": branch_n.id})
        self.assertEqual(new.mirabilenet_region_id, self.norte)
        with self.assertRaises(AccessError):
            Warehouse.create({"name": "Ajeno", "code": "TAJE",
                              "mirabilenet_branch_id": self.wh_s.mirabilenet_branch_id.id})
        with self.assertRaises(AccessError):
            self.env["stock.warehouse"].with_user(self.tecnico_n).create(
                {"name": "X", "code": "TXXX", "mirabilenet_branch_id": branch_n.id})

    def test_wizard(self):
        wizard = self.env["mirabilenet.inventory.move.wizard"].with_user(self.almacen_n).create({
            "kind": "compra", "product_id": self.onu.id, "lot_name": "SN-W",
            "dest_id": self.wh_n.id})
        wizard.action_confirm()
        lot = self.env["stock.lot"].search([("name", "=", "SN-W")])
        self.assertEqual(lot.mirabilenet_state, "en_almacen")
