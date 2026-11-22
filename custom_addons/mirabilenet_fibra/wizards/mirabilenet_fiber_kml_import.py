import base64
import difflib
import json
import re

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..fibra import deduce, geo, kml, parsing

#: Desde esta similitud de nombres se propone una coincidencia (sin confirmar).
PROBABLE_RATIO = 0.6


class MirabilenetFiberKmlImport(models.TransientModel):
    """Importa recorridos (LineString) y cajas (Point) de un KML/KMZ de Google Earth."""
    _name = "mirabilenet.fiber.kml.import"
    _description = "MIRABILENET: importar KML/KMZ"

    region_id = fields.Many2one("mirabilenet.region", string="Región", required=True,
                                default=lambda self: self.env.user.mirabilenet_region_id)
    file = fields.Binary(string="Archivo KML o KMZ", required=True, attachment=False)
    filename = fields.Char(string="Nombre del archivo")
    state = fields.Selection([("upload", "Archivo"), ("match", "Coincidencias"),
                              ("done", "Resumen")], default="upload")
    line_ids = fields.One2many("mirabilenet.fiber.kml.import.line", "wizard_id",
                               string="Coincidencias")
    log = fields.Text(string="Registro", readonly=True)

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "name": _("Importar KML/KMZ"),
        }

    @staticmethod
    def _code_in(text, codes):
        """Código conocido escrito dentro del nombre del placemark."""
        upper = (text or "").upper()
        for code in sorted(codes, key=len, reverse=True):
            if re.search(r"(?<![A-Z0-9-])%s(?![A-Z0-9-])" % re.escape(code.upper()), upper):
                return code
        return None

    def _match_segment(self, name, segments):
        by_code = {s.code: s for s in segments}
        code = self._code_in(name, by_code)
        if code:
            return by_code[code], "exacta", _("código en el nombre")
        key = deduce.compact_key(name)
        for segment in segments:
            if key and deduce.compact_key(segment.name) == key:
                return segment, "exacta", _("mismo nombre")
        best, ratio = None, 0.0
        for segment in segments:
            score = difflib.SequenceMatcher(None, key, deduce.compact_key(segment.name)).ratio()
            if score > ratio:
                best, ratio = segment, score
        if best and ratio >= PROBABLE_RATIO:
            return best, "probable", _("nombre parecido (%s %%)", int(ratio * 100))
        return False, "ninguna", _("sin coincidencia")

    def _match_nap(self, name, naps):
        by_code = {n.code: n for n in naps}
        code = self._code_in(name, by_code)
        if code:
            return by_code[code], "exacta", _("código en el nombre")
        key = parsing.normalize_key(name)
        same = naps.filtered(lambda n: key and parsing.normalize_key(n.name) == key)
        if len(same) == 1:
            return same, "exacta", _("mismo nombre NAP")
        if len(same) > 1:
            return same[0], "probable", _("nombre NAP repetido en %s; elija la correcta",
                                          ", ".join(same.mapped("code")))
        return False, "ninguna", _("sin coincidencia")

    def action_parse(self):
        self.ensure_one()
        try:
            items = kml.parse_kml(base64.b64decode(self.file))
        except kml.KmlError as error:
            raise UserError(str(error)) from error
        if not items:
            raise UserError(_("El archivo no tiene recorridos ni puntos."))
        domain = [("region_id", "=", self.region_id.id)]
        segments = self.env["mirabilenet.fiber.segment"].search(domain)
        naps = self.env["mirabilenet.fiber.nap"].search(domain)
        lines = []
        for item in items:
            if item["kind"] == "line":
                record, quality, note = self._match_segment(item["name"], segments)
                field = "segment_id"
            else:
                record, quality, note = self._match_nap(item["name"], naps)
                field = "nap_id"
            lines.append((0, 0, {
                "kind": item["kind"],
                "kml_name": item["name"],
                "kml_color": item["color"] or False,
                "points_json": json.dumps(item["points"]),
                "vertex_count": len(item["points"]),
                "kml_length_m": round(geo.path_length(item["points"]), 1),
                field: record.id if record else False,
                "match_quality": quality,
                "match_note": note,
                # Lo dudoso no se aplica sin que alguien lo confirme.
                "confirm": quality == "exacta",
            }))
        self.write({"line_ids": [(5, 0, 0)] + lines, "state": "match"})
        return self._reopen()

    def action_apply(self):
        self.ensure_one()
        log = []
        updated = 0
        for line in self.line_ids.filtered("confirm"):
            points = json.loads(line.points_json or "[]")
            if line.kind == "line":
                if not line.segment_id:
                    log.append(_("%s: confirmado sin tramo, se omite.", line.kml_name))
                    continue
                warning = line.segment_id.set_geometry(points)
                if line.kml_color:
                    line.segment_id.color = line.kml_color
                updated += 1
                if warning:
                    log.append("%s: %s" % (line.segment_id.code, warning))
            else:
                if not line.nap_id:
                    log.append(_("%s: confirmado sin NAP, se omite.", line.kml_name))
                    continue
                lat, lon = points[0]
                line.nap_id.write({"latitude": lat, "longitude": lon})
                line.nap_id.message_post(body=_("Ubicación tomada del KML «%s».",
                                                self.filename or ""))
                updated += 1
        skipped = len(self.line_ids) - len(self.line_ids.filtered("confirm"))
        log.insert(0, _("Actualizados: %(updated)s. Sin confirmar: %(skipped)s.",
                        updated=updated, skipped=skipped))
        self.write({"state": "done", "log": "\n".join(log)})
        return self._reopen()
