import base64
import os
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tests.common import BaseCase

from odoo.addons.mirabilenet_isp.isp import vault
from odoo.addons.mirabilenet_whatsapp.whatsapp import n8n
from odoo.addons.mirabilenet_whatsapp.whatsapp.gateway import FakeMetaGateway

from ..personal import interprete, limpieza


@tagged("mirabilenet", "post_install", "-at_install")
class TestLimpiezaPersonal(BaseCase):

    def test_roles_and_numbers(self):
        rows, errors = limpieza.limpiar([
            {"fila": 2, "nombre": " Ana  Pérez ", "usuario": "Ana.P", "rol": "Técnico",
             "whatsapp": "7123 4567", "zonas": "Z1, z1; Z2"},
            {"fila": 3, "nombre": "Pedro", "usuario": "pedro", "rol": "Subgerente"},
            {"fila": 4, "nombre": "Sin rol", "usuario": "x", "rol": "astronauta"},
            {"fila": 5, "nombre": "Repetido", "usuario": "ana.p", "rol": "cajero"},
            {"fila": 6, "nombre": "Mismo número", "usuario": "otro", "rol": "cajero",
             "whatsapp": "+591 71234567"},
        ])
        self.assertEqual([r["usuario"] for r in rows], ["ana.p", "pedro"])
        self.assertEqual(rows[0]["nombre"], "Ana Pérez")
        self.assertEqual(rows[0]["rol"], "tecnico")
        self.assertEqual(rows[0]["whatsapp"], "59171234567")
        self.assertEqual(rows[0]["zonas"], ["Z1", "Z2"])
        self.assertEqual(rows[1]["rol"], "admin_regional")
        self.assertEqual([e[0] for e in errors], [4, 5, 6])

    def test_reads_the_template(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "plantillas",
                            "plantilla_personal.csv")
        with open(path, "rb") as f:
            rows, missing = limpieza.leer_csv(f.read())
        self.assertFalse(missing)
        clean, errors = limpieza.limpiar(rows)
        self.assertFalse(errors)
        self.assertEqual(len(clean), 6)

    def test_free_text(self):
        self.assertEqual(interprete.accion("Ya quedó, era el conector"), "arreglado")
        self.assertEqual(interprete.accion("No se pudo arreglar, falta material"), "no_resuelto")
        self.assertEqual(interprete.accion("voy en camino"), "en_camino")
        self.assertIsNone(interprete.accion("buenos días"))


@tagged("mirabilenet", "post_install", "-at_install")
class TestPersonal(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.startClassPatcher(patch.dict(os.environ, {vault.ENV_VAR: "clave-de-prueba"}))
        Param = cls.env["ir.config_parameter"]
        Param.set_param("mirabilenet.meta_gateway", "fake")
        FakeMetaGateway.reset()
        cls.region = cls.env["mirabilenet.region"].create(
            {"code": "P-N", "name": "Norte personal", "wg_region_id": 41})
        cls.branch = cls.env["mirabilenet.branch"].create(
            {"region_id": cls.region.id, "code": "PN1", "name": "Central personal"})
        Zone = cls.env["mirabilenet.zone"]
        cls.zone_a = Zone.create({"region_id": cls.region.id, "code": "P-ZA", "name": "Zona A"})
        cls.zone_b = Zone.create({"region_id": cls.region.id, "code": "P-ZB", "name": "Zona B"})
        cls.node_a = cls.env["mirabilenet.node"].create(
            {"zone_id": cls.zone_a.id, "code": "P-NA", "name": "Nodo A"})
        cls.settings = cls.env["mirabilenet.whatsapp.settings"]._load()
        cls.settings.write({"active_messaging": True, "test_mode": False, "waba_id": "WABA-P",
                            "access_token": "token-meta", "app_secret": "secreto-app",
                            "webhook_verify_token": "verificame", "hour_start": 0,
                            "hour_end": 24, "require_consent": False})
        cls.number = cls.env["mirabilenet.whatsapp.number"].create(
            {"branch_id": cls.branch.id, "phone_number_id": "PN-P",
             "display_number": "+59170000009"})
        cls.env["mirabilenet.whatsapp.template"].create(
            {"event": "servicio_reparado", "meta_name": "servicio_reparado",
             "variables": "cliente, sucursal"})
        cls.jefe = cls._user("p_jefe", "admin_regional", "70000010")
        cls.tec_a = cls._user("p_tec_a", "tecnico", "70000011", zones=cls.zone_a,
                              boss=cls.jefe)
        cls.tec_a2 = cls._user("p_tec_a2", "tecnico", "70000012", zones=cls.zone_a)
        cls.tec_b = cls._user("p_tec_b", "tecnico", "70000013", zones=cls.zone_b)
        cls.pasante = cls._user("p_pasante", "pasante", "70000014")
        cls.plan = cls.env["product.template"].create({
            "name": "Plan personal", "type": "service", "mirabilenet_is_plan": True,
            "mirabilenet_plan_code": "P-PLAN", "list_price": 100,
            "mirabilenet_down_mbps": 20, "mirabilenet_up_mbps": 10})
        cls.customer = cls.env["res.partner"].create({
            "name": "Cliente Prueba", "mirabilenet_is_customer": True,
            "mirabilenet_region_id": cls.region.id, "phone": "70000099"})
        cls.service = cls.env["mirabilenet.service"].create({
            "partner_id": cls.customer.id, "plan_id": cls.plan.id, "node_id": cls.node_a.id,
            "install_address": "Calle Falsa 123"})
        cls.nap = cls.env["mirabilenet.fiber.nap"].create(
            {"code": "P-NAP-1", "region_id": cls.region.id, "latitude": -17.4,
             "longitude": -63.9, "address_reference": "Esquina del mercado"})
        port = cls.nap.port_ids[:1]
        port.write({"service_id": cls.service.id, "state": "ocupado"})

    @classmethod
    def _user(cls, login, role, whatsapp, zones=None, boss=None):
        user = new_test_user(cls.env, login, groups="base.group_user", name=login.upper())
        user.write({"mirabilenet_role": role, "mirabilenet_region_id": cls.region.id,
                    "mirabilenet_whatsapp": whatsapp,
                    "mirabilenet_zone_ids": [(6, 0, zones.ids)] if zones else False,
                    "mirabilenet_supervisor_id": boss.id if boss else False})
        return user

    def setUp(self):
        super().setUp()
        FakeMetaGateway.reset()

    def _failure(self, **vals):
        return self.env["maintenance.request"].create(dict(
            {"name": "Sin servicio: Cliente Prueba", "mirabilenet_service_id": self.service.id},
            **vals))

    def _send(self):
        self.env["mirabilenet.staff.notice"]._cron_dispatch()
        sent = list(FakeMetaGateway.sent)
        FakeMetaGateway.sent.clear()
        return sent

    def _incoming(self, user, **message):
        payload = dict({"from": user.mirabilenet_whatsapp, "id": "wamid.IN%s" % id(message),
                        "timestamp": "1795400000"}, **message)
        return self.env["mirabilenet.conversation"]._process_meta_incoming(payload, "PN-P")

    def _press(self, user, notice, action):
        return self._incoming(user, type="button", button={
            "payload": "mnp:%s:%s" % (notice.id, action), "text": action})

    def test_failure_goes_to_the_zone_technician_with_the_box_data(self):
        failure = self._failure()
        self.assertEqual(failure.user_id, self.tec_a)
        self.assertEqual(failure.mirabilenet_dispatch_state, "avisado")
        self.assertEqual(failure.mirabilenet_fiber_nap_id, self.nap)
        sent = self._send()
        self.assertEqual(len(sent), 1)
        message = sent[0]
        self.assertEqual(message["kind"], "template")
        self.assertEqual(message["plantilla"], "averia_asignada")
        self.assertEqual(message["destino"], "59170000011")
        params = message["parametros"]
        self.assertIn("Cliente Prueba", params)
        self.assertIn("Calle Falsa 123", params)
        self.assertTrue(any("P-NAP-1" in p for p in params))
        self.assertTrue(any("google.com/maps" in p for p in params))
        notice = failure.mirabilenet_notice_ids
        self.assertEqual(message["botones"], ["mnp:%s:en_camino" % notice.id,
                                              "mnp:%s:arreglado" % notice.id,
                                              "mnp:%s:no_resuelto" % notice.id])
        # El segundo va al técnico de la zona con menos averías abiertas.
        self.assertEqual(self._failure().user_id, self.tec_a2)

    def test_fixed_from_whatsapp_closes_and_tells_everyone(self):
        failure = self._failure()
        self._send()
        notice = failure.mirabilenet_notice_ids
        self.assertEqual(self._press(self.tec_a, notice, "en_camino"), "personal")
        self.assertEqual(failure.mirabilenet_dispatch_state, "en_camino")
        self._press(self.tec_a, notice, "arreglado")
        self.assertTrue(failure.stage_id.done)
        self.assertEqual(failure.mirabilenet_dispatch_state, "arreglado")
        # El cliente recibe «servicio reparado».
        to_customer = self.env["mirabilenet.whatsapp.message"].search(
            [("partner_id", "=", self.customer.id), ("event", "=", "servicio_reparado")])
        self.assertEqual(len(to_customer), 1)
        # Los demás técnicos de la zona se enteran; el de otra zona y el que la cerró, no.
        informed = self.env["mirabilenet.staff.notice"].search(
            [("request_id", "=", failure.id), ("kind", "=", "averia_resuelta")])
        self.assertEqual(informed.user_id, self.tec_a2)
        sent = self._send()
        sessions = [m for m in sent if m["kind"] == "session"]
        self.assertTrue(any("quedó cerrada" in m["contenido"]["texto"] for m in sessions))
        # El mensaje del técnico no abre una conversación de cliente.
        self.assertFalse(self.env["mirabilenet.conversation"].search(
            [("contact", "=", self.tec_a.mirabilenet_whatsapp)]))

    def test_not_fixed_asks_why_and_tells_the_boss(self):
        failure = self._failure()
        self._send()
        notice = failure.mirabilenet_notice_ids
        self._press(self.tec_a, notice, "no_resuelto")
        self.assertEqual(notice.awaiting, "nota")
        self.assertFalse(failure.stage_id.done)
        self._incoming(self.tec_a, type="text", text={"body": "Falta un conector, vuelvo mañana"})
        self.assertEqual(failure.mirabilenet_dispatch_state, "no_resuelto")
        self.assertEqual(failure.mirabilenet_result_note, "Falta un conector, vuelvo mañana")
        to_boss = self.env["mirabilenet.staff.notice"].search(
            [("request_id", "=", failure.id), ("kind", "=", "averia_no_resuelta")])
        self.assertEqual(to_boss.user_id, self.jefe)
        self.assertEqual(to_boss.parameters["nota"], "Falta un conector, vuelvo mañana")

    def test_free_text_without_n8n_and_foreign_buttons(self):
        failure = self._failure()
        self._incoming(self.tec_a, type="text", text={"body": "ya quedó funcionando"})
        self.assertTrue(failure.stage_id.done)
        # Un botón de un aviso ajeno no hace nada.
        other = self._failure()
        notice = other.mirabilenet_notice_ids.filtered(lambda n: n.kind == "averia_asignada")
        self._press(self.tec_b, notice, "arreglado")
        self.assertFalse(other.stage_id.done)

    def test_reminders_when_nobody_answers(self):
        failure = self._failure()
        failure.mirabilenet_assigned_at = fields.Datetime.now() - timedelta(hours=2)
        self.env["maintenance.request"]._cron_mirabilenet_reminders()
        kinds = self.env["mirabilenet.staff.notice"].search(
            [("request_id", "=", failure.id)]).mapped(lambda n: (n.kind, n.user_id))
        self.assertIn(("averia_recordatorio", self.tec_a), kinds)
        self.assertIn(("averia_sin_atender", self.jefe), kinds)
        self.assertTrue(failure.mirabilenet_reminded)
        # No se repite.
        count = self.env["mirabilenet.staff.notice"].search_count([("request_id", "=", failure.id)])
        self.env["maintenance.request"]._cron_mirabilenet_reminders()
        self.assertEqual(self.env["mirabilenet.staff.notice"].search_count(
            [("request_id", "=", failure.id)]), count)

    def test_task_for_an_intern(self):
        project = self.env["project.project"].create({"name": "Proyecto personal"})
        task = self.env["project.task"].create({"name": "Ordenar el depósito",
                                                "project_id": project.id,
                                                "user_ids": [(6, 0, self.pasante.ids)]})
        notice = self.env["mirabilenet.staff.notice"].search([("task_id", "=", task.id)])
        self.assertEqual(notice.kind, "tarea_asignada")
        self.assertEqual(notice.user_id, self.pasante)
        self._send()
        self._press(self.pasante, notice, "terminada")
        self.assertEqual(task.state, "1_done")
        # Una nota personal sin proyecto (como la bienvenida de Odoo) no se avisa.
        self.env["project.task"].create({"name": "Nota personal",
                                         "user_ids": [(6, 0, self.pasante.ids)]})
        self.assertEqual(self.env["mirabilenet.staff.notice"].search_count(
            [("user_id", "=", self.pasante.id), ("kind", "=", "tarea_asignada")]), 1)

    def test_old_notices_are_not_sent_late(self):
        failure = self._failure()
        notice = failure.mirabilenet_notice_ids
        self.env.cr.execute("UPDATE mirabilenet_staff_notice SET create_date = %s WHERE id = %s",
                            (fields.Datetime.now() - timedelta(hours=30), notice.id))
        notice.invalidate_recordset()
        self.assertEqual(self._send(), [])
        self.assertEqual(notice.state, "descartado")

    def test_free_text_goes_to_n8n_when_configured(self):
        Param = self.env["ir.config_parameter"]
        Param.set_param("mirabilenet.n8n_staff_webhook_url",
                        "http://127.0.0.1:5679/webhook/mirabilenet-personal")
        Param.set_param("mirabilenet.n8n_client", "fake")
        n8n.FakeN8NClient.reset()
        failure = self._failure()
        with patch.dict(os.environ, {n8n.SECRET_ENV: "secreto-de-firma-de-32-caracteres!!"}):
            self._incoming(self.tec_a, type="text", text={"body": "era el conector, ya está"})
            self.assertFalse(failure.stage_id.done)
            self.env["mirabilenet.staff.inbox"]._cron_deliver()
        event = n8n.FakeN8NClient.received[-1]["payload"]
        self.assertEqual(event["evento"], "mensaje_personal")
        self.assertEqual(event["averias_abiertas"][0]["id"], failure.id)
        status, body = self.env["mirabilenet.staff.inbox"]._apply_result(
            {"mensaje_id": event["mensaje_id"], "accion": "arreglado",
             "respuesta": "Perfecto, la cerré."})
        self.assertEqual((status, body["resultado"]), (200, "arreglado"))
        self.assertTrue(failure.stage_id.done)

    def test_import_staff(self):
        csv_text = ("nombre;usuario;correo;whatsapp;rol;region;sucursal;zonas;jefe;activo\n"
                    "Rosa Nueva;rosa.nueva;rosa@ejemplo.bo;70000020;tecnico;P-N;PN1;P-ZB;"
                    "beto.nuevo;si\n"
                    "Beto Nuevo;beto.nuevo;;70000021;subgerente;P-N;;;;si\n"
                    "Mal Rol;mal;;;astronauta;P-N;;;;si\n"
                    "Zona Rara;zona.rara;;;tecnico;P-N;;NO-EXISTE;;si\n")
        wizard = self.env["mirabilenet.staff.import"].create(
            {"file": base64.b64encode(("﻿" + csv_text).encode("utf-8")),
             "filename": "personal.csv"})
        wizard.action_preview()
        self.assertEqual(wizard.state, "preview")
        self.assertFalse(self.env["res.users"].search([("login", "=", "rosa.nueva")]))
        wizard.action_import()
        rosa = self.env["res.users"].search([("login", "=", "rosa.nueva")])
        beto = self.env["res.users"].search([("login", "=", "beto.nuevo")])
        self.assertEqual(rosa.mirabilenet_role, "tecnico")
        self.assertEqual(rosa.mirabilenet_branch_id, self.branch)
        self.assertEqual(rosa.mirabilenet_whatsapp, "59170000020")
        self.assertEqual(rosa.mirabilenet_zone_ids, self.zone_b)
        self.assertEqual(rosa.mirabilenet_supervisor_id, beto)
        self.assertEqual(beto.mirabilenet_role, "admin_regional")
        review = base64.b64decode(wizard.review_file).decode("utf-8-sig")
        self.assertIn("astronauta", review)
        self.assertIn("NO-EXISTE", review)

    def test_intern_task_says_check_the_platform(self):
        Task = self.env["project.task"]
        if "mirabilenet_internship" not in Task._fields:
            self.skipTest("Sin el módulo de pasantías.")
        Notice = self.env["mirabilenet.staff.notice"]
        project = self.env["project.project"].create(
            {"name": "Pasantía de prueba", "mirabilenet_internship": True})
        task = Task.create({"name": "Soporte del motor", "project_id": project.id,
                            "user_ids": [(6, 0, self.pasante.ids)],
                            "child_ids": [(0, 0, {"name": "Medir el eje",
                                                  "project_id": project.id})]})
        # Asignada pero sin publicar: el pasante todavía no la ve, no se le avisa.
        self.assertFalse(Notice.search([("user_id", "=", self.pasante.id)]))
        task.mirabilenet_published = True
        notice = Notice.search([("user_id", "=", self.pasante.id)])
        self.assertEqual(len(notice), 1)
        self.assertEqual(notice.kind, "tarea_pasante")
        self.assertIn("/odoo/project.task/%d" % task.id, notice.parameters["enlace"])
        task.mirabilenet_published = True  # volver a guardar no repite el aviso
        self.assertEqual(Notice.search_count([("user_id", "=", self.pasante.id)]), 1)
        sent = self._send()
        self.assertEqual(sent[-1]["plantilla"], "tarea_pasante")
        self.assertEqual(len(sent[-1]["botones"]), 1)
        self._press(self.pasante, notice, "recibido")
        self.assertNotEqual(task.state, "1_done")
