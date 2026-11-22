import base64
import copy
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..fibra import deduce, geo, parsing

NAP_COLUMNS = {
    "codigo", "nombre_nap", "localidad", "zona_barrio", "ramal", "latitud", "longitud",
    "direccion_referencia", "puertos_totales", "puertos_ocupados", "puertos_danados", "olt",
    "puerto_pon", "color_de_hilo_alimentador", "estado",
}
SEGMENT_COLUMNS = {
    "codigo", "nombre", "tipo", "longitud_m", "vertices", "naps_en_ruta", "lat_inicio",
    "lon_inicio", "lat_fin", "lon_fin", "hilos", "tipo_cable", "estado", "color",
    "geometria_json",
}
NAP_STATE_ALIASES = {"activo": "activa", "inactivo": "inactiva", "danado": "danada",
                     "verificar": "por_verificar", "pendiente": "por_verificar"}
SEGMENT_STATE_ALIASES = {"activo": "activa", "verificar": "por_verificar",
                         "pendiente": "por_verificar"}
SEGMENT_TYPE_ALIASES = {"troncal_principal": "troncal", "feeder": "alimentador",
                        "distribucion_secundaria": "distribucion"}
#: Campos que una corrección deducida puede cambiar.
NAP_DEDUCED = ("branch_line", "pon_port")
SEGMENT_DEDUCED = ("name", "color", "branch_line")


class MirabilenetFiberCsvImport(models.TransientModel):
    """Importa los CSV del relevamiento: NAP y tramos, juntos o por separado."""
    _name = "mirabilenet.fiber.csv.import"
    _description = "MIRABILENET: importar NAP y tramos desde CSV"

    region_id = fields.Many2one("mirabilenet.region", string="Región", required=True,
                                default=lambda self: self.env.user.mirabilenet_region_id)
    nap_file = fields.Binary(string="CSV de NAP", attachment=False)
    nap_filename = fields.Char(string="Archivo de NAP")
    segment_file = fields.Binary(string="CSV de tramos", attachment=False)
    segment_filename = fields.Char(string="Archivo de tramos")
    keep_existing = fields.Boolean(
        string="Conservar los datos ya cargados",
        help="Para completar con un archivo de otro día: llena lo que está vacío y, si un dato "
             "ya cargado viene distinto (por ejemplo, corregido en Odoo), lo conserva y lo "
             "anota. Apagado, el archivo manda y cada dato reemplazado queda en el registro.")
    apply_deductions = fields.Boolean(
        string="Aplicar correcciones deducidas", default=True,
        help="Completa ramales y puertos PON, unifica la escritura de los ramales, corrige "
             "tildes y asigna colores a los tramos. Todo queda en el registro.")
    lat_min = fields.Float(string="Latitud mínima", digits=(10, 7),
                           default=parsing.DEFAULT_LAT_BOUNDS[0])
    lat_max = fields.Float(string="Latitud máxima", digits=(10, 7),
                           default=parsing.DEFAULT_LAT_BOUNDS[1])
    lon_min = fields.Float(string="Longitud mínima", digits=(10, 7),
                           default=parsing.DEFAULT_LON_BOUNDS[0])
    lon_max = fields.Float(string="Longitud máxima", digits=(10, 7),
                           default=parsing.DEFAULT_LON_BOUNDS[1])

    state = fields.Selection([("draft", "Datos"), ("done", "Resumen")], default="draft")
    nap_created = fields.Integer(string="NAP creadas", readonly=True)
    nap_updated = fields.Integer(string="NAP actualizadas", readonly=True)
    segment_created = fields.Integer(string="Tramos creados", readonly=True)
    segment_updated = fields.Integer(string="Tramos actualizados", readonly=True)
    deduced_count = fields.Integer(string="Correcciones deducidas", readonly=True)
    flagged_count = fields.Integer(string="Marcados «revisar en campo»", readonly=True)
    rejected_count = fields.Integer(string="Coordenadas rechazadas", readonly=True)
    warning_count = fields.Integer(string="Avisos", readonly=True)
    error_count = fields.Integer(string="Filas con error", readonly=True)
    log = fields.Text(string="Registro", readonly=True)

    # ------------------------------------------------------------------
    def _bounds(self):
        return (self.lat_min, self.lat_max), (self.lon_min, self.lon_max)

    @staticmethod
    def _read(data, filename):
        try:
            return parsing.read_csv(base64.b64decode(data))
        except (ValueError, UnicodeError) as error:
            raise UserError(_("No se pudo leer %(file)s: %(error)s", file=filename or "",
                              error=error)) from error

    def _coordinate(self, row, column, bounds, label, report):
        text = row.get(column) or ""
        value = parsing.parse_coordinate(text, bounds)
        if text and value is None:
            report.reject(row, _("%(label)s «%(text)s» fuera de la zona o ilegible; se "
                                 "importa vacía", label=label, text=text))
        return value

    def _parse_naps(self, rows, report):
        lat_bounds, lon_bounds = self._bounds()
        naps = []
        for row in rows:
            code = (row.get("codigo") or "").strip()
            if not code:
                report.error(row, _("falta el código"))
                continue
            values = {
                "code": code, "_line": row["__line__"], "_row": row,
                "name": row.get("nombre_nap") or "",
                "locality": row.get("localidad") or "",
                "neighborhood": row.get("zona_barrio") or "",
                "branch_line": row.get("ramal") or "",
                "address_reference": row.get("direccion_referencia") or "",
                "olt": row.get("olt") or "",
                "pon_port": row.get("puerto_pon") or "",
                "feeder_color": row.get("color_de_hilo_alimentador") or "",
                "latitude": self._coordinate(row, "latitud", lat_bounds, _("latitud"), report),
                "longitude": self._coordinate(row, "longitud", lon_bounds, _("longitud"),
                                              report),
            }
            try:
                for column, field in (("puertos_totales", "port_count"),
                                      ("puertos_ocupados", "reported_ports_used"),
                                      ("puertos_danados", "reported_ports_damaged")):
                    values[field] = parsing.parse_integer(row.get(column))
            except ValueError as error:
                report.error(row, str(error))
                continue
            if values["port_count"] is not None and not 8 <= values["port_count"] <= 16:
                report.warn(code, _("puertos_totales «%s» fuera de 8 a 16; queda sin definir",
                                    values["port_count"]))
                values["port_count"] = None
            state = parsing.normalize_choice(row.get("estado"), dict(
                self.env["mirabilenet.fiber.nap"]._fields["state"].selection),
                NAP_STATE_ALIASES)
            if row.get("estado") and not state:
                report.warn(code, _("estado «%s» desconocido; queda por verificar",
                                    row.get("estado")))
            values["state"] = state
            naps.append(values)
        return naps

    def _parse_segments(self, rows, report):
        lat_bounds, lon_bounds = self._bounds()
        Segment = self.env["mirabilenet.fiber.segment"]
        types = dict(Segment._fields["segment_type"].selection)
        states = dict(Segment._fields["state"].selection)
        segments = []
        for row in rows:
            code = (row.get("codigo") or "").strip()
            if not code:
                report.error(row, _("falta el código"))
                continue
            values = {
                "code": code, "_line": row["__line__"], "_row": row,
                "name": row.get("nombre") or "",
                "cable_type": row.get("tipo_cable") or "",
                "nap_codes": parsing.parse_route_codes(row.get("naps_en_ruta")),
                "start_latitude": self._coordinate(row, "lat_inicio", lat_bounds,
                                                   _("latitud de inicio"), report),
                "start_longitude": self._coordinate(row, "lon_inicio", lon_bounds,
                                                    _("longitud de inicio"), report),
                "end_latitude": self._coordinate(row, "lat_fin", lat_bounds,
                                                 _("latitud de fin"), report),
                "end_longitude": self._coordinate(row, "lon_fin", lon_bounds,
                                                  _("longitud de fin"), report),
                "color": "",
                "geometry": None,
            }
            try:
                values["length_m"] = parsing.parse_decimal(row.get("longitud_m"))
                values["vertex_count"] = parsing.parse_integer(row.get("vertices"))
                values["fiber_count"] = parsing.parse_integer(row.get("hilos"))
            except ValueError as error:
                report.error(row, str(error))
                continue
            values["segment_type"] = parsing.normalize_choice(row.get("tipo"), types,
                                                              SEGMENT_TYPE_ALIASES)
            if row.get("tipo") and not values["segment_type"]:
                report.warn(code, _("tipo «%s» desconocido; queda distribución",
                                    row.get("tipo")))
            values["state"] = parsing.normalize_choice(row.get("estado"), states,
                                                       SEGMENT_STATE_ALIASES)
            if row.get("estado") and not values["state"]:
                report.warn(code, _("estado «%s» desconocido; queda por verificar",
                                    row.get("estado")))
            color = (row.get("color") or "").strip()
            if color and not color.startswith("#"):
                color = geo.kml_color_to_hex(color) if len(color) == 8 else "#" + color
            if color and (len(color) != 7 or not all(
                    c in "0123456789abcdefABCDEF" for c in color[1:])):
                report.warn(code, _("color «%s» no válido; se ignora", row.get("color")))
                color = ""
            values["color"] = color
            if row.get("geometria_json"):
                try:
                    values["geometry"] = geo.parse_geometry(row["geometria_json"], lat_bounds,
                                                            lon_bounds)
                except ValueError as error:
                    report.reject(row, _("geometría rechazada (%s); se importa vacía", error))
            segments.append(values)
        return segments

    # ------------------------------------------------------------------
    def _existing_naps(self):
        return [{
            "code": nap.code, "name": nap.name or "", "branch_line": nap.branch_line or "",
            "pon_port": nap.pon_port or "", "_record": nap,
            "latitude": nap.latitude if (nap.latitude or nap.longitude) else None,
            "longitude": nap.longitude if (nap.latitude or nap.longitude) else None,
        } for nap in self.env["mirabilenet.fiber.nap"].search(
            [("region_id", "=", self.region_id.id)])]

    def _existing_segments(self):
        return [{
            "code": s.code, "name": s.name or "", "segment_type": s.segment_type,
            "length_m": s.length_m, "color": s.color or "", "_record": s,
            "nap_codes": [stop.nap_id.code for stop in s.stop_ids.sorted("sequence")],
            "start_latitude": s.start_latitude or None, "start_longitude":
                s.start_longitude or None, "end_latitude": s.end_latitude or None,
            "end_longitude": s.end_longitude or None,
        } for s in self.env["mirabilenet.fiber.segment"].search(
            [("region_id", "=", self.region_id.id)])]

    @staticmethod
    def _set(vals, field, value, record):
        """Un dato vacío no borra lo que ya hay ni inventa uno: queda el valor por defecto."""
        if value in (None, ""):
            return
        vals[field] = value

    def _prefill(self, items, model, field_names):
        Model = self.env[model].with_context(active_test=False)
        csv_items = [v for v in items if "_record" not in v]
        records = {r.code: r for r in Model.search(
            [("code", "in", [v["code"] for v in csv_items])])}
        for values in csv_items:
            record = records.get(values["code"])
            for field in field_names if record else ():
                if not values.get(field) and record[field]:
                    values[field] = record[field]

    def _upsert(self, model, values, fields_map, report, counters):
        Model = self.env[model].with_context(active_test=False)
        record = Model.search([("code", "=", values["code"])], limit=1)
        if record and record.region_id != self.region_id:
            report.error(values["_row"], _("el código %(code)s ya existe en la región "
                                           "%(region)s", code=values["code"],
                                           region=record.region_id.display_name))
            return None
        vals = {}
        for field in fields_map:
            self._set(vals, field, values.get(field), record)
        if record:
            self._compare_existing(record, vals, values["code"], report)
        try:
            with self.env.cr.savepoint():
                if record:
                    record.write(vals)
                    counters["updated"] += 1
                else:
                    vals.update({"code": values["code"], "region_id": self.region_id.id})
                    record = Model.create(vals)
                    counters["created"] += 1
        except (UserError, ValidationError) as error:
            report.error(values["_row"], error.args[0] if error.args else str(error))
            return None
        return record

    #: Valores que equivalen a «todavía sin dato»: completarlos no es reemplazar nada.
    PLACEHOLDERS = {"state": "por_verificar"}

    def _compare_existing(self, record, vals, code, report):
        """Antes de escribir sobre un registro ya cargado: anota cada dato que cambia y, con
        «Conservar los datos ya cargados», deja el que había."""
        for field in list(vals):
            current, new = record[field], vals[field]
            if current in (None, False, "", 0, 0.0) or current == self.PLACEHOLDERS.get(field):
                continue
            if isinstance(current, float):
                if abs(current - float(new or 0)) < 1e-7:
                    continue
            elif str(current).strip() == str(new).strip():
                continue
            label = record._fields[field].string
            if self.keep_existing:
                del vals[field]
                report.warn(code, _("%(field)s distinto: en Odoo «%(old)s», en el archivo "
                                    "«%(new)s» (se conserva)", field=label, old=current,
                                    new=new))
            else:
                report.lines.append(_("%(code)s: actualizado: %(field)s «%(old)s» → «%(new)s»",
                                      code=code, field=label, old=current, new=new))

    def action_import(self):
        self.ensure_one()
        if not (self.nap_file or self.segment_file):
            raise UserError(_("Suba el CSV de NAP, el de tramos o ambos."))
        report = _Report()
        nap_rows = segment_rows = []
        if self.nap_file:
            columns, nap_rows = self._read(self.nap_file, self.nap_filename)
            if "codigo" not in columns:
                raise UserError(_("El CSV de NAP no tiene la columna «codigo»."))
            for column in sorted(set(columns) - NAP_COLUMNS - {""}):
                report.warn(_("CSV de NAP"), _("columna desconocida «%s», se ignora", column))
        if self.segment_file:
            columns, segment_rows = self._read(self.segment_file, self.segment_filename)
            if "codigo" not in columns:
                raise UserError(_("El CSV de tramos no tiene la columna «codigo»."))
            for column in sorted(set(columns) - SEGMENT_COLUMNS - {""}):
                report.warn(_("CSV de tramos"), _("columna desconocida «%s», se ignora",
                                                  column))
        naps = self._parse_naps(nap_rows, report) if self.nap_file else self._existing_naps()
        segments = (self._parse_segments(segment_rows, report) if self.segment_file
                    else self._existing_segments())

        # Lo que ya se cargó o corrigió a mano no lo pisa una deducción.
        self._prefill(naps, "mirabilenet.fiber.nap", ("branch_line", "pon_port"))
        self._prefill(segments, "mirabilenet.fiber.segment", ("color",))

        # Deducciones: con la opción apagada se calculan sobre una copia, solo para marcar.
        if self.apply_deductions:
            deduction = deduce.deduce(naps, segments)
        else:
            deduction = deduce.deduce(copy.deepcopy(
                [{k: v for k, v in n.items() if k != "_record"} for n in naps]),
                copy.deepcopy([{k: v for k, v in s.items() if k != "_record"}
                               for s in segments]))
            deduction.corrections = []
        report.lines.extend(deduction.lines())

        nap_counters = {"created": 0, "updated": 0}
        nap_records = {}
        nap_fields = ("name", "locality", "neighborhood", "branch_line", "address_reference",
                      "olt", "pon_port", "feeder_color", "latitude", "longitude",
                      "port_count", "reported_ports_used", "reported_ports_damaged", "state")
        for values in naps:
            if "_record" in values:
                record = values["_record"]
                vals = {f: values[f] for f in NAP_DEDUCED if values.get(f) != (record[f] or "")}
                if vals:
                    record.write(vals)
            else:
                record = self._upsert("mirabilenet.fiber.nap", values, nap_fields, report,
                                      nap_counters)
            if record:
                nap_records[values["code"]] = record
        for record in nap_records.values():
            note = record._mark_reported_damage() if self.nap_file else None
            if note:
                report.warn(record.code, note)

        segment_counters = {"created": 0, "updated": 0}
        segment_records = {}
        segment_fields = ("name", "segment_type", "length_m", "vertex_count", "start_latitude",
                          "start_longitude", "end_latitude", "end_longitude", "fiber_count",
                          "cable_type", "state", "color", "branch_line")
        Nap = self.env["mirabilenet.fiber.nap"]
        for values in segments:
            if "_record" in values:
                record = values["_record"]
                vals = {f: values[f] for f in SEGMENT_DEDUCED
                        if values.get(f) and values.get(f) != (record[f] or "")}
                if vals:
                    record.write(vals)
                segment_records[values["code"]] = record
                continue
            record = self._upsert("mirabilenet.fiber.segment", values, segment_fields, report,
                                  segment_counters)
            if not record:
                continue
            segment_records[values["code"]] = record
            if values.get("geometry"):
                record.geometry_json = json.dumps(values["geometry"])
            route = Nap.browse()
            for code in values["nap_codes"]:
                nap = nap_records.get(code) or Nap.search(
                    [("code", "=", code), ("region_id", "=", self.region_id.id)], limit=1)
                if nap:
                    route |= nap
                else:
                    report.warn(values["code"], _("NAP en ruta inexistente: %s", code))
                    report.flag(values["code"], _("NAP en ruta inexistente: %s", code))
            record._set_route(route)

        # Marcas «revisar en campo»: las de esta importación reemplazan las anteriores.
        flags = {code: list(texts) for code, texts in deduction.flags.items()}
        for code, texts in report.flags.items():
            flags.setdefault(code, []).extend(texts)
        flagged = 0
        for records in (nap_records, segment_records):
            for code, record in records.items():
                texts = flags.get(code, [])
                record.write({"needs_review": bool(texts),
                              "review_note": "\n".join(texts) or False})
                flagged += bool(texts)

        self.write({
            "state": "done",
            "nap_created": nap_counters["created"],
            "nap_updated": nap_counters["updated"],
            "segment_created": segment_counters["created"],
            "segment_updated": segment_counters["updated"],
            "deduced_count": len(deduction.corrections),
            "flagged_count": flagged,
            "rejected_count": report.rejected,
            "warning_count": report.warnings + len(deduction.warnings),
            "error_count": report.errors,
            "log": "\n".join(report.lines) or _("Sin observaciones."),
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "name": _("Resumen de la importación"),
        }


class _Report:
    """Registro de la importación: errores, avisos y coordenadas rechazadas."""

    def __init__(self):
        self.lines = []
        self.flags = {}
        self.errors = self.warnings = self.rejected = 0

    def error(self, row, text):
        self.errors += 1
        self.lines.append("Línea %s (%s): error: %s" % (
            row.get("__line__"), row.get("codigo") or "-", text))

    def warn(self, code, text):
        self.warnings += 1
        self.lines.append("%s: %s" % (code, text))

    def reject(self, row, text):
        self.rejected += 1
        code = row.get("codigo") or "-"
        self.lines.append("Línea %s (%s): coordenada rechazada: %s" % (
            row.get("__line__"), code, text))
        self.flag(code, "coordenada rechazada en la importación: %s" % text)

    def flag(self, code, text):
        self.flags.setdefault(code, []).append(text)
