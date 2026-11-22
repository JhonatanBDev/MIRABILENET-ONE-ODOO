import base64
import io
import json
import logging
import os
import zipfile

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

from ..fibra import deduce, geo, kml, parsing

_logger = logging.getLogger(__name__)

LAT = parsing.DEFAULT_LAT_BOUNDS
LON = parsing.DEFAULT_LON_BOUNDS
REAL_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "Static", "cvs naps"))

KML_TEXT = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
  <Style id="rojo"><LineStyle><color>ff0000ff</color><width>4</width></LineStyle></Style>
  <Style id="verde"><LineStyle><color>ff00ff00</color></LineStyle></Style>
  <StyleMap id="rojo_map">
    <Pair><key>normal</key><styleUrl>#rojo</styleUrl></Pair>
    <Pair><key>highlight</key><styleUrl>#verde</styleUrl></Pair>
  </StyleMap>
  <Folder>
    <Placemark><name>Ruta T: Central - 1T a 2T</name><styleUrl>#rojo_map</styleUrl>
      <LineString><coordinates>
        -63.8800,-17.4000,0 -63.8810,-17.4010,0 -63.8820,-17.4020,0
      </coordinates></LineString></Placemark>
    <Placemark><name>Ruta T Central 1T a 2T (copia)</name>
      <Style><LineStyle><color>ffff0000</color></LineStyle></Style>
      <LineString><coordinates>-63.88,-17.40 -63.89,-17.41</coordinates></LineString></Placemark>
    <Placemark><name>1T</name><Point><coordinates>-63.884567,-17.404864,0</coordinates></Point></Placemark>
  </Folder>
</Document></kml>"""


class FiberCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Region = cls.env["mirabilenet.region"]
        cls.norte = Region.create({"code": "F-N", "name": "Fibra Norte", "wg_region_id": 41})
        cls.sur = Region.create({"code": "F-S", "name": "Fibra Sur", "wg_region_id": 42})
        cls.gestor_n = cls._user("f_gestor_n", "admin_regional", cls.norte)
        cls.tecnico_n = cls._user("f_tecnico_n", "tecnico", cls.norte)
        cls.tecnico_s = cls._user("f_tecnico_s", "tecnico", cls.sur)
        cls.cajero_n = cls._user("f_cajero_n", "cajero", cls.norte)

        Partner = cls.env["res.partner"]
        cls.cliente_n = Partner.create({
            "name": "Cliente Fibra Norte", "mirabilenet_is_customer": True,
            "mirabilenet_region_id": cls.norte.id, "phone": "70000001",
            "partner_latitude": -17.401, "partner_longitude": -63.881})
        cls.cliente_n2 = Partner.create({
            "name": "Cliente Fibra Norte 2", "mirabilenet_is_customer": True,
            "mirabilenet_region_id": cls.norte.id})
        cls.plan_n = cls.env["product.template"].create({
            "name": "F-NORTE", "type": "service", "mirabilenet_is_plan": True,
            "mirabilenet_plan_code": "F-NORTE", "list_price": 200,
            "mirabilenet_region_id": cls.norte.id, "mirabilenet_down_mbps": 20,
            "mirabilenet_up_mbps": 10, "mirabilenet_reduced_profile": "F-NORTE-REDUCIDO"})
        Service = cls.env["mirabilenet.service"]
        cls.service = Service.create({"partner_id": cls.cliente_n.id, "plan_id": cls.plan_n.id})
        cls.service2 = Service.create({"partner_id": cls.cliente_n2.id,
                                       "plan_id": cls.plan_n.id})
        cls.nap = cls.env["mirabilenet.fiber.nap"].create({
            "code": "F-YAP-01", "name": "1F", "region_id": cls.norte.id, "port_count": 8,
            "branch_line": "Ruta F", "neighborhood": "Centro", "state": "activa",
            "latitude": -17.4, "longitude": -63.88})

    @classmethod
    def _user(cls, login, role, region=None):
        user = new_test_user(cls.env, login, groups="base.group_user")
        user.write({"mirabilenet_role": role,
                    "mirabilenet_region_id": region.id if region else False})
        return user

    def _port(self, number, nap=None):
        return (nap or self.nap).port_ids.filtered(lambda p: p.number == number)

    def _import(self, nap_csv=None, segment_csv=None, **extra):
        vals = {"region_id": self.norte.id}
        if nap_csv is not None:
            vals.update(nap_file=base64.b64encode(nap_csv), nap_filename="naps.csv")
        if segment_csv is not None:
            vals.update(segment_file=base64.b64encode(segment_csv),
                        segment_filename="tramos.csv")
        vals.update(extra)
        wizard = self.env["mirabilenet.fiber.csv.import"].create(vals)
        wizard.action_import()
        return wizard


@tagged("mirabilenet", "post_install", "-at_install")
class TestFiberParsers(TransactionCase):
    """Lógica pura: no toca la base."""

    def test_coordinates(self):
        self.assertAlmostEqual(parsing.parse_coordinate("-17.404.864", LAT), -17.404864)
        self.assertAlmostEqual(parsing.parse_coordinate("-63.884.567", LON), -63.884567)
        self.assertAlmostEqual(parsing.parse_coordinate("-174.055.798.604.324", LAT),
                               -17.4055798604324)
        self.assertAlmostEqual(parsing.parse_coordinate("-6.388.524.129.690.300", LON),
                               -63.885241296903)
        self.assertAlmostEqual(parsing.parse_coordinate("-1.741.648.787.684.930", LAT),
                               -17.4164878768493)
        self.assertAlmostEqual(parsing.parse_coordinate("-638.830.638.226.115", LON),
                               -63.8830638226115)
        # Fuera de la zona, ilegible o vacía: None.
        self.assertIsNone(parsing.parse_coordinate("-6.388.524", LAT))
        self.assertIsNone(parsing.parse_coordinate("-17.404.864", LON))
        self.assertIsNone(parsing.parse_coordinate("-16.904.864", LAT))
        self.assertIsNone(parsing.parse_coordinate("abc", LAT))
        self.assertIsNone(parsing.parse_coordinate("", LAT))
        self.assertIsNone(parsing.parse_coordinate("-1", LAT))

    def test_numbers_and_headers(self):
        self.assertEqual(parsing.parse_decimal("3140.0"), 3140.0)
        self.assertEqual(parsing.parse_decimal("3140,5"), 3140.5)
        self.assertEqual(parsing.parse_decimal("1.234,5"), 1234.5)
        self.assertEqual(parsing.parse_integer("16"), 16)
        self.assertIsNone(parsing.parse_integer(""))
        with self.assertRaises(ValueError):
            parsing.parse_integer("dieciséis")
        self.assertEqual(parsing.normalize_key("﻿Color de hilo alimentador "),
                         "color_de_hilo_alimentador")
        self.assertEqual(parsing.normalize_key("Zona/Barrio"), "zona_barrio")
        self.assertEqual(parsing.normalize_key("Código"), "codigo")

    def test_route_codes(self):
        self.assertEqual(
            parsing.parse_route_codes("B1 (YAP-B-01), 1D (YAP-D-01), K (YAP-K-00), "
                                      "6K (YAP-K-06-B), B1 (YAP-B-01)"),
            ["YAP-B-01", "YAP-D-01", "YAP-K-00", "YAP-K-06-B"])
        self.assertEqual(parsing.parse_route_codes(""), [])
        self.assertEqual(parsing.parse_route_codes("sin códigos"), [])

    def test_read_csv(self):
        data = ("﻿Código;Nombre NAP\r\nA;1\r\n;\r\n\r\nB;2\r\n").encode("utf-8")
        columns, rows = parsing.read_csv(data)
        self.assertEqual(columns, ["codigo", "nombre_nap"])
        self.assertEqual([r["codigo"] for r in rows], ["A", "B"])

    def test_colors_and_distance(self):
        self.assertEqual(geo.kml_color_to_hex("ff0000ff"), "#ff0000")
        self.assertEqual(geo.kml_color_to_hex("7f00ff00"), "#00ff00")
        self.assertEqual(geo.kml_color_to_hex("FFFF0000"), "#0000ff")
        self.assertIsNone(geo.kml_color_to_hex("zz"))
        # Un grado de latitud ronda los 111 km.
        self.assertAlmostEqual(geo.haversine(0, 0, 1, 0), 111195, delta=10)
        self.assertAlmostEqual(geo.path_length([[0, 0], [0.5, 0], [1, 0]]), 111195, delta=10)
        self.assertEqual(geo.nap_marker_status("danada", 8, 8), "danada")
        self.assertEqual(geo.nap_marker_status("activa", 0, 0), "sin_datos")
        self.assertEqual(geo.nap_marker_status("por_verificar", 8, 8), "sin_datos")
        self.assertEqual(geo.nap_marker_status("activa", 8, 0), "llena")
        self.assertEqual(geo.nap_marker_status("activa", 8, 2), "casi_llena")
        self.assertEqual(geo.nap_marker_status("activa", 8, 5), "libre")

    def test_kml(self):
        items = kml.parse_kml(KML_TEXT.encode("utf-8"))
        lines = [i for i in items if i["kind"] == "line"]
        points = [i for i in items if i["kind"] == "point"]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["name"], "Ruta T: Central - 1T a 2T")
        self.assertEqual(lines[0]["color"], "#ff0000", "StyleMap → estilo normal")
        self.assertEqual(lines[1]["color"], "#0000ff", "estilo propio del placemark")
        self.assertEqual(lines[0]["points"][0], [-17.4, -63.88], "lon,lat → [lat, lon]")
        self.assertEqual(len(lines[0]["points"]), 3)
        self.assertEqual(points[0]["name"], "1T")
        self.assertEqual(points[0]["points"], [[-17.404864, -63.884567]])
        with self.assertRaises(kml.KmlError):
            kml.parse_kml(b"<kml><no-cierra>")

    def test_kmz(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("files/leeme.txt", "x")
            archive.writestr("doc.kml", KML_TEXT)
        items = kml.parse_kml(buffer.getvalue())
        self.assertEqual(len(items), 3)
        empty = io.BytesIO()
        with zipfile.ZipFile(empty, "w") as archive:
            archive.writestr("leeme.txt", "x")
        with self.assertRaises(kml.KmlError):
            kml.parse_kml(empty.getvalue())


@tagged("mirabilenet", "post_install", "-at_install")
class TestFiberDeductions(TransactionCase):
    """Reglas de corrección deducidas, con datos sintéticos."""

    def _nap(self, code, name, branch="", pon="", lat=-17.40, lon=-63.88):
        return {"code": code, "name": name, "branch_line": branch, "pon_port": pon,
                "latitude": lat, "longitude": lon}

    def _seg(self, code, name, kind, codes, length=0.0, start=None, end=None):
        return {"code": code, "name": name, "segment_type": kind, "length_m": length,
                "nap_codes": codes, "color": "",
                "start_latitude": start[0] if start else None,
                "start_longitude": start[1] if start else None,
                "end_latitude": end[0] if end else None,
                "end_longitude": end[1] if end else None}

    def test_segment_label(self):
        self.assertEqual(deduce.segment_label("5IZ: RAMAL 1 - 1A a 3A"), "5IZ")
        self.assertEqual(deduce.segment_label("Ruta D: Central - 1D a 8D"), "Ruta D")
        self.assertEqual(deduce.segment_label("F.O 24 H: RAMAL 3 - 2P (NODO)"), "F.O 24 H")
        self.assertEqual(deduce.segment_label("Troncal Central - RAMAL 4"), "Troncal Central")
        self.assertEqual(deduce.series_of("YAP-H2-01"), "H2")
        self.assertEqual(deduce.series_of("YAP-K-06-B"), "K")

    def test_branch_fill_and_ambiguity(self):
        naps = [self._nap("YAP-A-01", "1A"), self._nap("YAP-A-02", "2A"),
                self._nap("YAP-T-01", "1T"), self._nap("YAP-X-01", "1X"),
                self._nap("YAP-Z-01", "1Z"), self._nap("YAP-Q-01", "1Q", "Ya cargado")]
        segments = [
            self._seg("TR-1", "Troncal Central - RAMAL 4", "troncal",
                      ["YAP-T-01", "YAP-A-01", "YAP-Z-01"]),
            # YAP-A-01 es donde arranca el ramal 5IZ: queda en el troncal.
            self._seg("TR-2", "5IZ: RAMAL 1 - 1A a 2A", "distribucion",
                      ["YAP-A-01", "YAP-A-02"]),
            self._seg("TR-3", "Ruta X: 1X", "distribucion", ["YAP-Q-01", "YAP-X-01"]),
            self._seg("TR-4", "Ruta Y: 1X", "distribucion", ["YAP-Q-01", "YAP-X-01"]),
        ]
        result = deduce.deduce(naps, segments)
        by_code = {n["code"]: n for n in naps}
        self.assertEqual(by_code["YAP-A-02"]["branch_line"], "5IZ")
        self.assertEqual(by_code["YAP-A-01"]["branch_line"], "Troncal Central")
        self.assertEqual(by_code["YAP-T-01"]["branch_line"], "Troncal Central")
        self.assertEqual(by_code["YAP-X-01"]["branch_line"], "", "dos ramales: ambiguo")
        self.assertEqual(by_code["YAP-Q-01"]["branch_line"], "Ya cargado")
        self.assertTrue(any(c == "YAP-X-01" and "ambiguo" in t for c, t in result.warnings))
        self.assertTrue(any("deducido: branch_line" in line for line in result.lines()))

    def test_derived_branch_yields_to_parent(self):
        naps = [self._nap("YAP-K-00", "K"), self._nap("YAP-K-06", "6K"),
                self._nap("YAP-K-09", "K9"), self._nap("YAP-D-08", "8D")]
        segments = [
            self._seg("TR-2", "Ruta D: 8D - K - 6K", "distribucion",
                      ["YAP-D-08", "YAP-K-00", "YAP-K-06"]),
            self._seg("TR-3", "Ruta K sur: 6K - K - K9", "distribucion",
                      ["YAP-K-06", "YAP-K-00", "YAP-K-09"]),
        ]
        deduce.deduce(naps, segments)
        self.assertEqual([n["branch_line"] for n in naps], ["Ruta D", "Ruta D", "Ruta K sur", "Ruta D"])

    def test_branch_unify_and_accents(self):
        naps = [self._nap("YAP-M-01", "1M", "RUTA B/ ESPAÑA,SAN FRANCISCO Y FLORESTA"),
                self._nap("YAP-P-01", "1P", "F.O de 24 H."),
                self._nap("YAP-M-02", "2M")]
        segments = [
            self._seg("TR-18", "Ruta B/ Espana, San Francisco y Floresta: 2P - 1M a 6M",
                      "distribucion", ["YAP-M-01", "YAP-M-02"]),
            self._seg("TR-17", "F.O 24 H: RAMAL 3 - 2P (NODO)", "alimentador", ["YAP-P-01"]),
        ]
        deduce.deduce(naps, segments)
        self.assertEqual(segments[0]["name"],
                         "Ruta B/ España, San Francisco y Floresta: 2P - 1M a 6M")
        canonical = "Ruta B/ España, San Francisco y Floresta"
        self.assertEqual(naps[0]["branch_line"], canonical)
        self.assertEqual(naps[2]["branch_line"], canonical)
        self.assertEqual(naps[1]["branch_line"], "F.O 24 H")
        self.assertEqual(deduce.fix_accents("ESPANA y espana"), "ESPAÑA y españa")

    def test_pon_port(self):
        naps = [self._nap("YAP-M-01", "1M", "R1", "7"), self._nap("YAP-M-02", "2M", "R1"),
                self._nap("YAP-N-01", "1N", "R1", "3"), self._nap("YAP-N-02", "2N", "R1", "4"),
                self._nap("YAP-N-03", "3N", "R1"), self._nap("YAP-M-03", "3M", "R2")]
        deduce.deduce(naps, [])
        self.assertEqual([n["pon_port"] for n in naps], ["7", "7", "3", "4", "", ""])

    def test_flags(self):
        naps = [self._nap("YAP-B-01", "B1", lat=-17.4050, lon=-63.8850),
                self._nap("YAP-B-02", "B2", lat=-17.4060, lon=-63.8850),
                self._nap("YAP-B-04", "B4", lat=-17.4250, lon=-63.8850)]
        segments = [
            self._seg("TR-26", "Ruta J norte: 4J - 5J a 8J (480M)", "distribucion",
                      ["YAP-B-01", "YAP-B-02"], length=954.1,
                      start=(-17.4050, -63.8850), end=(-17.4060, -63.8850)),
            self._seg("TR-24", "Ruta I ramal: 4I - 15I - 16I (210M)", "distribucion",
                      ["YAP-B-01", "YAP-B-02"], length=50.0,
                      start=(-17.4050, -63.8850), end=(-17.4060, -63.8850)),
            self._seg("TR-05", "3IZ: Reserva - 1E a 4E", "distribucion", ["YAP-B-01"],
                      length=1000, start=(-17.4100, -63.8850)),
        ]
        result = deduce.deduce(naps, segments)
        self.assertIn("YAP-B-04", result.flags)
        self.assertTrue(any("ningún tramo" in t for t in result.flags["YAP-B-04"]))
        self.assertTrue(any("probablemente errónea" in t for t in result.flags["YAP-B-04"]))
        self.assertNotIn("YAP-B-01", result.flags)
        self.assertTrue(any("480" in t for t in result.flags["TR-26"]))
        self.assertTrue(any("recorrido mínimo" in t for t in result.flags["TR-24"]))
        self.assertTrue(any("inicio" in t for t in result.flags["TR-05"]))
        self.assertEqual(naps[2]["latitude"], -17.4250, "las marcas no cambian datos")

    def test_colors(self):
        def segments():
            return [
                self._seg("TR-01", "Troncal Central - RAMAL 4", "troncal", []),
                self._seg("TR-17", "F.O 24 H: RAMAL 3 - 2P", "alimentador", []),
                self._seg("TR-23", "Ruta I: Central - 1I a 14I", "distribucion", []),
                self._seg("TR-24", "Ruta I ramal: 4I - 15I - 16I (210M)", "distribucion", []),
                self._seg("TR-04", "LINEA B: Central - B1 a B8", "distribucion", []),
                self._seg("TR-21", "Ruta H oeste: Central - 1H a 8H", "distribucion", []),
                self._seg("TR-25", "Ruta J norte: RAMAL 4 - 2J a 4J", "distribucion", []),
                self._seg("TR-26", "Ruta J norte: 4J - 5J a 8J (480M)", "distribucion", []),
                self._seg("TR-27", "Ruta J sur: RAMAL 4 - 9J a 16J", "distribucion", []),
            ]
        first, second = segments(), segments()
        deduce.deduce([], first)
        deduce.deduce([], list(reversed(second)))
        colors = {s["code"]: s["color"] for s in first}
        self.assertEqual(colors, {s["code"]: s["color"] for s in second}, "determinista")
        self.assertEqual(colors["TR-01"], "#f57c00")
        self.assertEqual(colors["TR-17"], "#8e24aa")
        self.assertEqual(colors["TR-24"], "#2962ff")
        self.assertEqual(colors["TR-25"], colors["TR-26"], "mismo ramal, mismo color")
        self.assertNotEqual(colors["TR-25"], colors["TR-27"])
        self.assertNotEqual(colors["TR-23"], colors["TR-04"])
        self.assertEqual(len(set(colors.values())), 8)
        # Un color ya cargado no se toca.
        kept = [dict(self._seg("TR-99", "Ruta Z: x", "distribucion", []), color="#123456")]
        deduce.deduce([], kept)
        self.assertEqual(kept[0]["color"], "#123456")


@tagged("mirabilenet", "post_install", "-at_install")
class TestFiberPorts(FiberCommon):

    def test_port_generation_and_safe_reduction(self):
        self.assertEqual(self.nap.port_ids.mapped("number"), list(range(1, 9)))
        self.assertEqual((self.nap.ports_free, self.nap.ports_used), (8, 0))
        self.nap.port_count = 12
        self.assertEqual(len(self.nap.port_ids), 12)
        self._port(10).service_id = self.service
        self.assertEqual(self._port(10).state, "ocupado")
        self.assertEqual(self.nap.ports_used, 1)
        self.assertAlmostEqual(self.nap.occupancy_rate, 100 / 12, places=1)
        with self.assertRaises(UserError):
            self.nap.port_count = 8
        self.assertEqual(len(self.nap.port_ids), 12)
        self._port(10).action_release()
        self._port(12).state = "danado"
        self.nap.port_count = 8
        self.assertEqual(len(self.nap.port_ids), 8)
        with self.assertRaises(ValidationError):
            self.nap.port_count = 5
        empty = self.env["mirabilenet.fiber.nap"].create(
            {"code": "F-YAP-00", "region_id": self.norte.id, "port_count": 0})
        self.assertFalse(empty.port_ids)
        self.assertTrue(empty.ports_missing)

    def test_assign_and_release_via_service(self):
        port = self._port(3)
        service = self.service.with_user(self.tecnico_n)
        with Form(service) as form:
            form.fiber_nap_id = self.nap.with_user(self.tecnico_n)
            form.fiber_port_id = port.with_user(self.tecnico_n)
        self.assertEqual((port.state, port.service_id, port.partner_id),
                         ("ocupado", self.service, self.cliente_n))
        self.assertTrue(port.assigned_date)
        self.assertEqual(self.service.fiber_nap_id, self.nap)
        self.assertEqual(self.cliente_n.mirabilenet_fiber_port_ids, port)
        self.assertEqual(self.cliente_n.mirabilenet_fiber_port_count, 1)
        # Cambiar de puerto libera el anterior.
        self.service.fiber_port_id = self._port(4)
        self.assertEqual((port.state, port.service_id.id), ("libre", False))
        self.assertEqual(self._port(4).state, "ocupado")
        self.service.fiber_port_id = False
        self.assertEqual(self._port(4).state, "libre")
        self.assertFalse(self.service.fiber_nap_id)

    def test_assign_and_release_via_port(self):
        port = self._port(5).with_user(self.tecnico_n)
        port.write({"service_id": self.service.id})
        self.assertEqual(self.service.fiber_port_id, self._port(5))
        self.assertEqual(self.service.fiber_nap_id, self.nap)
        port.write({"state": "libre"})
        self.assertFalse(port.service_id)
        self.assertFalse(self.service.fiber_port_id)
        # El usuario de fibra no cambia el número ni la NAP del puerto.
        with self.assertRaises(AccessError):
            port.write({"number": 99})
        # Nunca ocupado sin servicio.
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            self._port(6).write({"state": "ocupado"})
            self.env.flush_all()
        with self.assertRaises(UserError):
            self._port(7).write({"state": "danado"})
            self._port(7).write({"service_id": self.service.id})

    def test_assign_wizard(self):
        wizard = self.env["mirabilenet.fiber.port.assign"].with_user(self.tecnico_n).create({
            "nap_id": self.nap.id, "port_id": self._port(2).id,
            "service_id": self.service2.id})
        wizard.action_assign()
        self.assertEqual(self._port(2).service_id, self.service2)

    def test_one_port_per_service(self):
        self._port(1).service_id = self.service
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            self._port(2).service_id = self.service
            self.env.flush_all()

    def test_release_when_service_terminated(self):
        self._port(1).service_id = self.service
        self.service.sudo()._apply_confirmed_state("baja")
        self.assertEqual(self.service.state, "baja")
        self.assertEqual((self._port(1).state, self._port(1).service_id.id), ("libre", False))
        with self.assertRaises(UserError):
            self._port(1).service_id = self.service

    def test_region_isolation(self):
        self.assertTrue(self.nap.with_user(self.tecnico_n).read(["code"]))
        with self.assertRaises(AccessError):
            self.nap.with_user(self.tecnico_s).read(["code"])
        Nap = self.env["mirabilenet.fiber.nap"]
        self.assertFalse(Nap.with_user(self.tecnico_s).search([("code", "=", "F-YAP-01")]))
        with self.assertRaises(AccessError):
            self._port(1).with_user(self.tecnico_s).read(["state"])
        data = Nap.with_user(self.tecnico_s).get_fiber_map_data()
        self.assertNotIn(self.nap.id, [n["id"] for n in data["naps"]])
        # Quien no es de fibra no ve la red.
        with self.assertRaises(AccessError):
            self.nap.with_user(self.cajero_n).read(["code"])
        # El gestor no mueve una NAP a otra región.
        with self.assertRaises(AccessError):
            self.nap.with_user(self.gestor_n).write({"region_id": self.sur.id})

    def test_marker_move_only_manager(self):
        Nap = self.env["mirabilenet.fiber.nap"]
        with self.assertRaises(AccessError):
            Nap.with_user(self.tecnico_n).move_nap_marker(self.nap.id, -17.41, -63.89)
        self.assertEqual(self.nap.latitude, -17.4)
        Nap.with_user(self.gestor_n).move_nap_marker(self.nap.id, -17.41, -63.89)
        self.assertAlmostEqual(self.nap.latitude, -17.41)
        self.assertAlmostEqual(self.nap.longitude, -63.89)
        with self.assertRaises(UserError):
            Nap.with_user(self.gestor_n).move_nap_marker(self.nap.id, -117.41, -63.89)

    def test_map_data_and_warnings(self):
        self._port(1).service_id = self.service
        self.env["mirabilenet.fiber.nap"].create({
            "code": "F-YAP-02", "name": "2F", "region_id": self.norte.id, "port_count": 0,
            "latitude": -17.402, "longitude": -63.882, "needs_review": True,
            "review_note": "ubicación probablemente errónea"})
        segment = self.env["mirabilenet.fiber.segment"].create({
            "code": "F-TR-01", "name": "Ruta F: 1F", "region_id": self.norte.id,
            "start_latitude": -17.4, "start_longitude": -63.88,
            "end_latitude": -17.41, "end_longitude": -63.89})
        data = self.env["mirabilenet.fiber.nap"].with_user(self.tecnico_n).get_fiber_map_data()
        nap = next(n for n in data["naps"] if n["id"] == self.nap.id)
        self.assertEqual((nap["status"], nap["ports_free"]), ("libre", 7))
        line = next(s for s in data["segments"] if s["id"] == segment.id)
        self.assertTrue(line["dashed"], "sin geometría: recta discontinua")
        self.assertEqual(line["color"], geo.DEFAULT_SEGMENT_COLORS["distribucion"])
        self.assertEqual(line["branch_line"], "Ruta F")
        self.assertEqual([c["name"] for c in data["customers"]], ["Cliente Fibra Norte"])
        texts = {(w["code"], w["text"]) for w in data["warnings"]}
        self.assertIn(("F-YAP-02", "ubicación probablemente errónea"), texts)
        self.assertIn(("F-YAP-02", "Falta definir cantidad de puertos"), texts)
        self.assertTrue(any(w["model"] == "segment" for w in data["warnings"]))
        self.assertFalse(data["can_move"])
        segment.geometry_json = json.dumps([[-17.4, -63.88], [-17.401, -63.881]])
        data = self.env["mirabilenet.fiber.nap"].get_fiber_map_data()
        self.assertFalse(next(s for s in data["segments"] if s["id"] == segment.id)["dashed"])

    def test_low_occupancy(self):
        other = self.env["mirabilenet.fiber.nap"].create({
            "code": "F-YAP-03", "region_id": self.norte.id, "port_count": 8,
            "neighborhood": "Llena"})
        for port, service in zip(other.port_ids, (self.service, self.service2)):
            port.service_id = service
        self.env["ir.config_parameter"].set_param(
            "mirabilenet_fibra.low_occupancy_threshold", "20")
        Nap = self.env["mirabilenet.fiber.nap"]
        self.assertIn(self.nap, Nap.search([("low_occupancy", "=", True)]))
        self.assertNotIn(other, Nap.search([("low_occupancy", "=", True)]))
        action = Nap.action_low_occupancy_zones()
        found = Nap.search(action["domain"])
        self.assertIn(self.nap, found)
        self.assertNotIn(other, found)

    def test_maintenance_request(self):
        self._port(3).service_id = self.service
        request = self.env["maintenance.request"].create({
            "name": "Sin señal", "mirabilenet_service_id": self.service.id})
        self.assertEqual(request.mirabilenet_fiber_nap_id, self.nap)
        self.assertEqual(request.mirabilenet_fiber_port_id, self._port(3))
        self.assertEqual(self.nap.maintenance_count, 1)
        self.assertEqual(self.service.fiber_maintenance_count, 1)
        action = request.action_mirabilenet_fiber_map()
        self.assertEqual(action["params"], {"nap_id": self.nap.id})


@tagged("mirabilenet", "post_install", "-at_install")
class TestFiberImport(FiberCommon):

    NAP_CSV = (
        "﻿Código;Nombre NAP;Localidad;Zona / Barrio;Ramal;Latitud;Longitud;"
        "Puertos totales;Puertos dañados;Estado;Columna rara\r\n"
        "YAP-T-01;1T;Yapacani;Centro;;-17.404.864;-63.884.567;8;1;activa;x\r\n"
        "YAP-T-02;2T;Yapacani;;;-17.405.000;-63.885.000;;;Por verificar;\r\n"
        "YAP-T-03;3T;Yapacani;;;-6.388;-63.886.000;;;por_verificar;\r\n"
        ";;;;;;;;;;\r\n"
    ).encode("utf-8")
    SEGMENT_CSV = (
        "﻿codigo;nombre;tipo;longitud_m;vertices;naps_en_ruta;lat_inicio;lon_inicio;"
        "lat_fin;lon_fin;hilos;tipo_cable;estado\r\n"
        "TR-T1;Ruta T: Central - 1T a 3T;distribucion;300.0;5;1T (YAP-T-01), 2T (YAP-T-02), "
        "3T (YAP-T-03), X (YAP-ZZ-99);-174.048.640;-638.845.670;-174.050.000;-638.850.000;"
        ";;activa\r\n"
        ";;;;;;;;;;;;\r\n"
    ).encode("utf-8")

    def test_csv_import_idempotent(self):
        wizard = self._import(self.NAP_CSV, self.SEGMENT_CSV)
        self.assertEqual((wizard.nap_created, wizard.nap_updated), (3, 0))
        self.assertEqual((wizard.segment_created, wizard.segment_updated), (1, 0))
        self.assertEqual(wizard.error_count, 0, wizard.log)
        self.assertEqual(wizard.rejected_count, 1, wizard.log)
        self.assertIn("columna desconocida «columna_rara»", wizard.log)
        self.assertIn("YAP-ZZ-99", wizard.log)
        Nap = self.env["mirabilenet.fiber.nap"]
        nap1, nap2, nap3 = (Nap.search([("code", "=", c)]) for c in
                            ("YAP-T-01", "YAP-T-02", "YAP-T-03"))
        self.assertAlmostEqual(nap1.latitude, -17.404864)
        self.assertEqual((nap1.port_count, nap1.ports_damaged, nap1.state), (8, 1, "activa"))
        self.assertEqual(nap2.state, "por_verificar")
        # Sin cantidad en el CSV, la caja nueva nace con los puertos estándar (8).
        self.assertEqual((nap2.port_count, len(nap2.port_ids)), (8, 8))
        self.assertEqual(nap3.latitude, 0.0, "coordenada rechazada: vacía")
        self.assertTrue(nap3.needs_review)
        self.assertIn("coordenada rechazada", nap3.review_note)
        self.assertEqual(nap2.branch_line, "Ruta T", "deducido del tramo")
        self.assertIn("deducido: branch_line", wizard.log)
        segment = self.env["mirabilenet.fiber.segment"].search([("code", "=", "TR-T1")])
        self.assertEqual(segment.nap_ids.mapped("code"), ["YAP-T-01", "YAP-T-02", "YAP-T-03"])
        self.assertAlmostEqual(segment.start_latitude, -17.404864)
        self.assertTrue(segment.color)
        self.assertTrue(segment.needs_review, "NAP en ruta inexistente")

        # Segunda vez: actualiza, no crea. Lo editado a mano no se pisa.
        nap2.branch_line = "Ramal corregido"
        segment.color = "#123456"
        again = self._import(self.NAP_CSV, self.SEGMENT_CSV)
        self.assertEqual((again.nap_created, again.nap_updated), (0, 3))
        self.assertEqual((again.segment_created, again.segment_updated), (0, 1))
        self.assertEqual(Nap.search_count([("code", "like", "YAP-T-")]), 3)
        self.assertEqual(nap2.branch_line, "Ramal corregido")
        self.assertEqual(segment.color, "#123456")
        self.assertEqual(len(segment.stop_ids), 3)
        self.assertEqual(nap1.ports_damaged, 1, "no marca dañados de más")

    def test_import_without_deductions_and_region_conflict(self):
        wizard = self._import(self.NAP_CSV, self.SEGMENT_CSV, apply_deductions=False)
        self.assertEqual(wizard.deduced_count, 0)
        nap2 = self.env["mirabilenet.fiber.nap"].search([("code", "=", "YAP-T-02")])
        self.assertFalse(nap2.branch_line)
        other = self.env["mirabilenet.fiber.csv.import"].create({
            "region_id": self.sur.id, "nap_file": base64.b64encode(self.NAP_CSV)})
        other.action_import()
        self.assertEqual(other.error_count, 3, "los códigos ya existen en otra región")
        with self.assertRaises(UserError):
            self._import(b"nombre;otra\r\nA;B\r\n")

    def test_kml_wizard(self):
        self._import(self.NAP_CSV, self.SEGMENT_CSV)
        segment = self.env["mirabilenet.fiber.segment"].search([("code", "=", "TR-T1")])
        segment.write({"name": "Ruta T: Central - 1T a 2T", "length_m": 50.0,
                       "vertex_count": 2})
        wizard = self.env["mirabilenet.fiber.kml.import"].create({
            "region_id": self.norte.id, "file": base64.b64encode(KML_TEXT.encode("utf-8")),
            "filename": "red.kml"})
        wizard.action_parse()
        exact = wizard.line_ids.filtered(lambda l: l.kml_name == "Ruta T: Central - 1T a 2T")
        self.assertEqual((exact.segment_id, exact.match_quality, exact.confirm),
                         (segment, "exacta", True))
        dubious = wizard.line_ids.filtered(lambda l: l.kml_name == "Ruta T Central 1T a 2T (copia)")
        self.assertEqual((dubious.match_quality, dubious.confirm), ("probable", False))
        point = wizard.line_ids.filtered(lambda l: l.kind == "point")
        self.assertEqual(point.nap_id.code, "YAP-T-01")
        self.assertTrue(point.confirm)
        wizard.action_apply()
        self.assertEqual(segment.color, "#ff0000")
        self.assertEqual(segment.vertex_count, 3)
        self.assertAlmostEqual(segment.length_m, geo.path_length(
            [[-17.4, -63.88], [-17.401, -63.881], [-17.402, -63.882]]), delta=0.1)
        self.assertTrue(segment.has_geometry)
        self.assertIn("10 %", wizard.log)
        self.assertAlmostEqual(point.nap_id.latitude, -17.404864)

    def test_real_files(self):
        nap_path = os.path.join(REAL_DIR, "naps_yapacani.csv")
        segment_path = os.path.join(REAL_DIR, "tramos_fibra_mapa.csv")
        if not (os.path.exists(nap_path) and os.path.exists(segment_path)):
            self.skipTest("No están los CSV reales en %s" % REAL_DIR)
        with open(nap_path, "rb") as handle:
            nap_csv = handle.read()
        with open(segment_path, "rb") as handle:
            segment_csv = handle.read()
        _columns, nap_rows = parsing.read_csv(nap_csv)
        _columns, segment_rows = parsing.read_csv(segment_csv)
        empty_before = sum(1 for r in nap_rows if not r.get("ramal"))

        wizard = self._import(nap_csv, segment_csv)
        _logger.info(
            "CSV reales: NAP creadas %s, actualizadas %s; tramos creados %s, actualizados %s; "
            "deducidas %s; revisar en campo %s; coordenadas rechazadas %s; avisos %s; "
            "errores %s\n%s", wizard.nap_created, wizard.nap_updated,
            wizard.segment_created, wizard.segment_updated, wizard.deduced_count,
            wizard.flagged_count, wizard.rejected_count, wizard.warning_count,
            wizard.error_count, wizard.log)
        self.assertEqual((wizard.nap_created, wizard.segment_created), (112, 27))
        self.assertEqual(wizard.error_count, 0, wizard.log)

        # Cada coordenada fuera de la zona está en el registro.
        bad = set()
        for r in nap_rows:
            for column, bounds in (("latitud", LAT), ("longitud", LON)):
                if r.get(column) and parsing.parse_coordinate(r[column], bounds) is None:
                    bad.add(r["codigo"])
        for r in segment_rows:
            for column, bounds in (("lat_inicio", LAT), ("lon_inicio", LON),
                                   ("lat_fin", LAT), ("lon_fin", LON)):
                if r.get(column) and parsing.parse_coordinate(r[column], bounds) is None:
                    bad.add(r["codigo"])
        for code in bad:
            self.assertIn("(%s): coordenada rechazada" % code, wizard.log)
        # Cada código desconocido de naps_en_ruta está en el registro.
        known = {r["codigo"] for r in nap_rows}
        for r in segment_rows:
            for code in parsing.parse_route_codes(r.get("naps_en_ruta")):
                if code not in known:
                    self.assertIn("NAP en ruta inexistente: %s" % code, wizard.log)

        Nap = self.env["mirabilenet.fiber.nap"]
        Segment = self.env["mirabilenet.fiber.segment"]
        naps = Nap.search([("region_id", "=", self.norte.id), ("code", "=like", "YAP-%")])
        self.assertEqual(len(naps), 112)
        self.assertEqual(empty_before, 66)
        self.assertEqual(naps.filtered(lambda n: not n.branch_line).mapped("code"),
                         ["YAP-B-04"])
        b4 = Nap.search([("code", "=", "YAP-B-04")])
        self.assertTrue(b4.needs_review)
        self.assertIn("ningún tramo", b4.review_note)
        self.assertIn("probablemente errónea", b4.review_note)
        tr = {s.code: s for s in Segment.search([("region_id", "=", self.norte.id)])}
        self.assertTrue(tr["TR-26"].needs_review)
        self.assertTrue(tr["TR-24"].needs_review)
        self.assertIn("España", tr["TR-18"].name)
        self.assertIn("España", tr["TR-19"].name)
        self.assertEqual(tr["TR-24"].color, "#2962ff")
        self.assertEqual(tr["TR-01"].color, "#f57c00")
        self.assertEqual(tr["TR-25"].color, tr["TR-26"].color)
        self.assertEqual(len(tr["TR-23"].stop_ids), 15)

        again = self._import(nap_csv, segment_csv)
        self.assertEqual((again.nap_created, again.nap_updated), (0, 112))
        self.assertEqual((again.segment_created, again.segment_updated), (0, 27))
        self.assertEqual(Nap.search_count([("region_id", "=", self.norte.id),
                                           ("code", "=like", "YAP-%")]), 112)
        data = Nap.get_fiber_map_data()
        self.assertTrue(any(w["code"] == "YAP-B-04" for w in data["warnings"]))
