import json

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..fibra import deduce, geo

SEGMENT_TYPES = [
    ("troncal", "Troncal"),
    ("alimentador", "Alimentador"),
    ("distribucion", "Distribución"),
]
SEGMENT_STATES = [("activa", "Activa"), ("por_verificar", "Por verificar")]


class MirabilenetFiberSegment(models.Model):
    """Tramo de fibra: su recorrido por las calles y las NAP por las que pasa."""
    _name = "mirabilenet.fiber.segment"
    _description = "MIRABILENET: tramo de fibra"
    _inherit = ["mail.thread", "mirabilenet.region.scoped"]
    _order = "code"
    _rec_names_search = ["code", "name"]

    code = fields.Char(string="Código", required=True, index=True, tracking=True)
    name = fields.Char(string="Nombre", tracking=True)
    branch_line = fields.Char(string="Ramal", compute="_compute_branch_line", store=True,
                              readonly=False, index=True,
                              help="Lo que va antes de «:» en el nombre del tramo.")
    segment_type = fields.Selection(SEGMENT_TYPES, string="Tipo", default="distribucion",
                                    required=True, index=True, tracking=True)
    region_id = fields.Many2one("mirabilenet.region", string="Región", required=True,
                                ondelete="restrict", index=True, tracking=True,
                                default=lambda self: self.env.user.mirabilenet_region_id)
    company_id = fields.Many2one("res.company", string="Compañía", required=True,
                                 default=lambda self: self.env.company, index=True)
    active = fields.Boolean(string="Activo", default=True)
    state = fields.Selection(SEGMENT_STATES, string="Estado", default="por_verificar",
                             required=True, tracking=True)
    length_m = fields.Float(string="Longitud (m)", digits=(12, 1), tracking=True)
    vertex_count = fields.Integer(string="Vértices")
    start_latitude = fields.Float(string="Latitud de inicio", digits=(10, 7))
    start_longitude = fields.Float(string="Longitud de inicio", digits=(10, 7))
    end_latitude = fields.Float(string="Latitud de fin", digits=(10, 7))
    end_longitude = fields.Float(string="Longitud de fin", digits=(10, 7))
    fiber_count = fields.Integer(string="Hilos")
    cable_type = fields.Char(string="Tipo de cable")
    color = fields.Char(string="Color",
                        help="Color de la línea en el mapa. Vacío: el color de su tipo.")
    effective_color = fields.Char(string="Color en el mapa", compute="_compute_effective_color")
    geometry_json = fields.Text(
        string="Geometría",
        help="Lista ordenada de [lat, lon] con todos los vértices del recorrido real.")
    has_geometry = fields.Boolean(string="Tiene recorrido", compute="_compute_has_geometry",
                                  store=True)
    stop_ids = fields.One2many("mirabilenet.fiber.segment.stop", "segment_id",
                               string="NAP en ruta", copy=True)
    nap_ids = fields.Many2many("mirabilenet.fiber.nap", string="NAP",
                               compute="_compute_nap_ids", search="_search_nap_ids")
    notes = fields.Text(string="Notas")
    needs_review = fields.Boolean(string="Revisar en campo", index=True, tracking=True)
    review_note = fields.Text(string="Qué revisar")

    _code_uniq = models.Constraint("unique(code)", "Ya existe un tramo con ese código.")

    @api.depends("code", "name")
    def _compute_display_name(self):
        for segment in self:
            segment.display_name = ("%s %s" % (segment.code, segment.name)
                                    if segment.name else segment.code or "")

    @api.depends("name")
    def _compute_branch_line(self):
        for segment in self:
            segment.branch_line = deduce.segment_label(segment.name) or False

    @api.depends("color", "segment_type")
    def _compute_effective_color(self):
        for segment in self:
            segment.effective_color = geo.segment_color(segment.color, segment.segment_type)

    @api.depends("geometry_json")
    def _compute_has_geometry(self):
        for segment in self:
            try:
                segment.has_geometry = len(geo.parse_geometry(segment.geometry_json)) >= 2
            except ValueError:
                segment.has_geometry = False

    @api.depends("stop_ids.nap_id", "stop_ids.sequence")
    def _compute_nap_ids(self):
        for segment in self:
            segment.nap_ids = segment.stop_ids.sorted("sequence").nap_id

    def _search_nap_ids(self, operator, value):
        return [("stop_ids.nap_id", operator, value)]

    @api.constrains("geometry_json")
    def _check_geometry(self):
        for segment in self:
            try:
                geo.parse_geometry(segment.geometry_json)
            except ValueError as error:
                raise ValidationError(_("%(code)s: %(error)s", code=segment.code,
                                        error=error)) from error

    @api.constrains("color")
    def _check_color(self):
        for segment in self:
            color = segment.color or ""
            if color and not (len(color) in (4, 7) and color.startswith("#") and all(
                    c in "0123456789abcdefABCDEF" for c in color[1:])):
                raise ValidationError(_("El color va en formato #rrggbb."))

    def _route_points(self):
        """Recorrido para el mapa y si es el real (``False``: línea recta provisoria)."""
        self.ensure_one()
        try:
            points = geo.parse_geometry(self.geometry_json)
        except ValueError:
            points = []
        if len(points) >= 2:
            return points, True
        start = (self.start_latitude, self.start_longitude)
        end = (self.end_latitude, self.end_longitude)
        if any(start) and any(end):
            return [list(start), list(end)], False
        naps = [[s.nap_id.latitude, s.nap_id.longitude] for s in self.stop_ids.sorted(
            "sequence") if s.nap_id.latitude or s.nap_id.longitude]
        return (naps, False) if len(naps) >= 2 else ([], False)

    def _map_values(self):
        values = []
        type_labels = dict(SEGMENT_TYPES)
        for segment in self:
            points, real = segment._route_points()
            if not points:
                continue
            values.append({
                "id": segment.id,
                "code": segment.code,
                "name": segment.name or "",
                "branch_line": segment.branch_line or "",
                "type": segment.segment_type,
                "type_label": type_labels.get(segment.segment_type),
                "state": segment.state,
                "state_label": dict(SEGMENT_STATES).get(segment.state),
                "length_m": segment.length_m,
                "color": segment.effective_color,
                "points": points,
                "dashed": not real,
                "naps": [s.nap_id.code for s in segment.stop_ids.sorted("sequence")],
                "needs_review": segment.needs_review,
            })
        return values

    def _set_route(self, naps):
        """Reemplaza las NAP en ruta por ``naps`` (en orden)."""
        self.ensure_one()
        commands = [(5, 0, 0)] + [(0, 0, {"sequence": index, "nap_id": nap.id})
                                  for index, nap in enumerate(naps, start=1)]
        self.write({"stop_ids": commands})

    def set_geometry(self, points):
        """Guarda el recorrido y recalcula largo y vértices. Devuelve el aviso, si lo hay."""
        self.ensure_one()
        length = round(geo.path_length(points), 1)
        notes = []
        if geo.differs(self.length_m, length):
            notes.append(_("longitud %(old)s m → %(new)s m", old=self.length_m, new=length))
        if geo.differs(self.vertex_count, len(points)):
            notes.append(_("vértices %(old)s → %(new)s", old=self.vertex_count,
                           new=len(points)))
        self.write({
            "geometry_json": json.dumps(points),
            "length_m": length,
            "vertex_count": len(points),
            "start_latitude": points[0][0], "start_longitude": points[0][1],
            "end_latitude": points[-1][0], "end_longitude": points[-1][1],
        })
        if notes:
            message = _("La geometría difiere más de un 10 %% de lo cargado: %s",
                        "; ".join(notes))
            self.message_post(body=message)
            return message
        return None

    def action_open_map(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "mirabilenet_fibra.fiber_map",
            "name": _("Mapa de fibra"),
            "params": {"segment_id": self.id},
        }
