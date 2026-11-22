from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..fibra import geo

FIBER_MANAGER = "mirabilenet_fibra.group_mirabilenet_fiber_manager"
THRESHOLD_PARAM = "mirabilenet_fibra.low_occupancy_threshold"
DEFAULT_THRESHOLD = 30
MAP_TAG = "mirabilenet_fibra.fiber_map"

NAP_STATES = [
    ("activa", "Activa"),
    ("por_verificar", "Por verificar"),
    ("inactiva", "Inactiva"),
    ("danada", "Dañada"),
]


class MirabilenetFiberNap(models.Model):
    """Caja NAP: de 8 a 16 puertos que se asignan a servicios."""
    _name = "mirabilenet.fiber.nap"
    _description = "MIRABILENET: caja NAP"
    _inherit = ["mail.thread", "mirabilenet.region.scoped"]
    _order = "code"
    _rec_names_search = ["code", "name"]

    code = fields.Char(string="Código", required=True, index=True, tracking=True,
                       help="Único, por ejemplo YAP-D-01.")
    name = fields.Char(string="Nombre NAP", tracking=True,
                       help="Rótulo de la caja en el mapa (5H, 16I, B1). Puede repetirse.")
    region_id = fields.Many2one("mirabilenet.region", string="Región", required=True,
                                ondelete="restrict", index=True, tracking=True,
                                default=lambda self: self.env.user.mirabilenet_region_id)
    company_id = fields.Many2one("res.company", string="Compañía", required=True,
                                 default=lambda self: self.env.company, index=True)
    active = fields.Boolean(string="Activo", default=True)
    locality = fields.Char(string="Localidad")
    neighborhood = fields.Char(string="Zona o barrio", index=True)
    branch_line = fields.Char(string="Ramal", index=True, tracking=True)
    latitude = fields.Float(string="Latitud", digits=(10, 7), tracking=True)
    longitude = fields.Float(string="Longitud", digits=(10, 7), tracking=True)
    address_reference = fields.Char(string="Dirección o referencia")
    port_count = fields.Integer(
        string="Puertos totales", default=lambda self: self._default_port_count(),
        tracking=True,
        help="De 8 a 16. Una caja nueva toma los puertos estándar de los ajustes (8). Al "
             "cambiarlo se crean o quitan puertos; nunca se quita uno ocupado. 0 = no se sabe.")
    olt = fields.Char(string="OLT")
    pon_port = fields.Char(string="Puerto PON")
    feeder_color = fields.Char(string="Color del hilo alimentador")
    state = fields.Selection(NAP_STATES, string="Estado", default="por_verificar",
                             required=True, index=True, tracking=True)
    notes = fields.Text(string="Notas")
    reported_ports_used = fields.Integer(
        string="Ocupados según el relevamiento",
        help="Cifra del relevamiento, sin clientes identificados. No ocupa puertos.")
    reported_ports_damaged = fields.Integer(string="Dañados según el relevamiento")
    needs_review = fields.Boolean(string="Revisar en campo", index=True, tracking=True)
    review_note = fields.Text(string="Qué revisar")

    port_ids = fields.One2many("mirabilenet.fiber.port", "nap_id", string="Puertos")
    maps_url = fields.Char(string="Cómo llegar", compute="_compute_maps_url",
                           help="Ruta en Google Maps hasta la caja.")
    stop_ids = fields.One2many("mirabilenet.fiber.segment.stop", "nap_id",
                               string="Paso de tramos")
    ports_used = fields.Integer(string="Puertos ocupados", compute="_compute_ports",
                                store=True)
    ports_free = fields.Integer(string="Puertos libres", compute="_compute_ports", store=True)
    ports_damaged = fields.Integer(string="Puertos dañados", compute="_compute_ports",
                                   store=True)
    ports_reserved = fields.Integer(string="Puertos reservados", compute="_compute_ports",
                                    store=True)
    occupancy_rate = fields.Float(string="Ocupación (%)", compute="_compute_ports",
                                  store=True, aggregator="avg", digits=(5, 1))
    ports_missing = fields.Boolean(string="Falta definir cantidad de puertos",
                                   compute="_compute_ports_missing")
    low_occupancy = fields.Boolean(string="Baja ocupación", compute="_compute_low_occupancy",
                                   search="_search_low_occupancy")
    service_count = fields.Integer(string="Clientes", compute="_compute_counts")
    maintenance_count = fields.Integer(string="Averías", compute="_compute_counts")
    segment_count = fields.Integer(string="Tramos", compute="_compute_counts")

    _code_uniq = models.Constraint("unique(code)", "Ya existe una NAP con ese código.")
    _port_count_range = models.Constraint(
        "CHECK(port_count = 0 OR (port_count >= 8 AND port_count <= 16))",
        "Una NAP tiene de 8 a 16 puertos (0 mientras no se conozca).")
    _coordinates_range = models.Constraint(
        "CHECK(latitude >= -90 AND latitude <= 90 AND longitude >= -180 AND longitude <= 180)",
        "Coordenadas fuera de rango.")

    @api.depends("code", "name")
    def _compute_display_name(self):
        for nap in self:
            nap.display_name = ("%s (%s)" % (nap.code, nap.name) if nap.name and nap.code
                                else nap.code or nap.name or "")

    @api.model
    def _default_port_count(self):
        """Puertos estándar de una caja nueva (Ajustes de la red de fibra; 8 si no se tocó)."""
        value = self.env["ir.config_parameter"].sudo().get_param(
            "mirabilenet_fibra.default_port_count", "8")
        try:
            count = int(value)
        except (TypeError, ValueError):
            count = 8
        return count if 8 <= count <= 16 else 8

    @api.model
    def _mirabilenet_apply_standard_ports(self):
        """Lleva al estándar las cajas que todavía no tienen puertos. Devuelve cuántas cambió."""
        naps = self.sudo().with_context(active_test=False).search([("port_count", "=", 0)])
        naps.write({"port_count": self._default_port_count()})
        return len(naps)

    @api.depends("latitude", "longitude")
    def _compute_maps_url(self):
        for nap in self:
            nap.maps_url = (
                "https://www.google.com/maps/dir/?api=1&destination=%s,%s"
                % (nap.latitude, nap.longitude) if nap.latitude and nap.longitude else False)

    @api.depends("port_ids.state", "port_count")
    def _compute_ports(self):
        for nap in self:
            states = nap.port_ids.mapped("state")
            nap.ports_used = states.count("ocupado")
            nap.ports_free = states.count("libre")
            nap.ports_damaged = states.count("danado")
            nap.ports_reserved = states.count("reservado")
            nap.occupancy_rate = (100.0 * nap.ports_used / nap.port_count
                                  if nap.port_count else 0.0)

    @api.depends("port_count")
    def _compute_ports_missing(self):
        for nap in self:
            nap.ports_missing = not nap.port_count

    @api.model
    def _low_occupancy_threshold(self):
        value = self.env["ir.config_parameter"].sudo().get_param(THRESHOLD_PARAM)
        try:
            return float(value) if value not in (None, False, "") else DEFAULT_THRESHOLD
        except ValueError:
            return DEFAULT_THRESHOLD

    @api.depends("occupancy_rate", "port_count")
    def _compute_low_occupancy(self):
        threshold = self._low_occupancy_threshold()
        for nap in self:
            nap.low_occupancy = bool(nap.port_count) and nap.occupancy_rate < threshold

    def _search_low_occupancy(self, operator, value):
        if operator not in ("=", "!="):
            return NotImplemented
        domain = [("port_count", ">", 0),
                  ("occupancy_rate", "<", self._low_occupancy_threshold())]
        positive = (operator == "=") == bool(value)
        return domain if positive else ["!", "&"] + domain

    def _compute_counts(self):
        Service = self.env["mirabilenet.service"]
        Request = self.env["maintenance.request"]
        for nap in self:
            nap.service_count = Service.search_count([("fiber_nap_id", "=", nap.id)])
            nap.maintenance_count = Request.search_count(
                [("mirabilenet_fiber_nap_id", "=", nap.id)])
            nap.segment_count = len(nap.stop_ids.segment_id)

    # ------------------------------------------------------------------
    # Puertos
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        naps = super().create(vals_list)
        naps._sync_ports()
        return naps

    def write(self, vals):
        result = super().write(vals)
        if "port_count" in vals:
            self._sync_ports()
        return result

    def _sync_ports(self):
        """Crea los puertos que faltan y quita los que sobran, si están libres."""
        Port = self.env["mirabilenet.fiber.port"]
        for nap in self:
            numbers = set(nap.port_ids.mapped("number"))
            extra = nap.port_ids.filtered(lambda p: p.number > nap.port_count)
            blocked = extra.filtered(lambda p: p.service_id or p.state == "ocupado")
            if blocked:
                raise UserError(_(
                    "No se puede bajar %(nap)s a %(count)s puertos: los puertos %(ports)s "
                    "tienen un servicio asignado. Libérelos primero.",
                    nap=nap.display_name, count=nap.port_count,
                    ports=", ".join(str(n) for n in sorted(blocked.mapped("number")))))
            extra.unlink()
            missing = [n for n in range(1, nap.port_count + 1) if n not in numbers]
            if missing:
                Port.create([{"nap_id": nap.id, "number": n} for n in missing])

    @api.constrains("port_count")
    def _check_port_count(self):
        for nap in self:
            if nap.port_count and not 8 <= nap.port_count <= 16:
                raise ValidationError(_("Una NAP tiene de 8 a 16 puertos."))

    def _mark_reported_damage(self):
        """Marca como dañados tantos puertos libres como diga el relevamiento.

        Devuelve un aviso si no hay puertos suficientes; nunca crea puertos de más.
        """
        self.ensure_one()
        missing = self.reported_ports_damaged - self.ports_damaged
        if missing <= 0 or not self.port_count:
            return None
        free = self.port_ids.filtered(lambda p: p.state == "libre").sorted(
            "number", reverse=True)
        free[:missing].write({"state": "danado"})
        if len(free) < missing:
            return _("%(nap)s: el relevamiento dice %(n)s puertos dañados y solo había "
                     "%(free)s libres para marcar.", nap=self.code,
                     n=self.reported_ports_damaged, free=len(free))
        return None

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_open_map(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": MAP_TAG,
            "name": _("Mapa de fibra"),
            "params": {"nap_id": self.id},
        }

    def action_view_services(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Clientes de %s", self.code),
            "res_model": "mirabilenet.service",
            "view_mode": "list,form",
            "domain": [("fiber_nap_id", "=", self.id)],
        }

    def action_view_ports(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Puertos de %s", self.code),
            "res_model": "mirabilenet.fiber.port",
            "view_mode": "list,form",
            "domain": [("nap_id", "=", self.id)],
            "context": {"default_nap_id": self.id},
        }

    def action_view_maintenance(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Averías de %s", self.code),
            "res_model": "maintenance.request",
            "view_mode": "list,form",
            "domain": [("mirabilenet_fiber_nap_id", "=", self.id)],
            "context": {"default_mirabilenet_fiber_nap_id": self.id,
                        "default_maintenance_type": "corrective"},
        }

    def action_view_segments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Tramos de %s", self.code),
            "res_model": "mirabilenet.fiber.segment",
            "view_mode": "list,form",
            "domain": [("id", "in", self.stop_ids.segment_id.ids)],
        }

    @api.model
    def action_low_occupancy_zones(self):
        """NAP de las zonas cuya ocupación total está por debajo del umbral."""
        threshold = self._low_occupancy_threshold()
        groups = self._read_group(
            [("port_count", ">", 0)], ["region_id", "neighborhood"],
            ["ports_used:sum", "port_count:sum"])
        zones = [(region.id, zone) for region, zone, used, total in groups
                 if total and 100.0 * used / total < threshold]
        domain = [("port_count", ">", 0)]
        if zones:
            terms = [["&", ("region_id", "=", region), ("neighborhood", "=", zone or False)]
                     for region, zone in zones]
            zone_domain = ["|"] * (len(terms) - 1) + [t for term in terms for t in term]
            domain = domain + zone_domain
        else:
            domain = [("id", "=", 0)]
        return {
            "type": "ir.actions.act_window",
            "name": _("Zonas con pocos clientes (ocupación < %s %%)", int(threshold)),
            "res_model": "mirabilenet.fiber.nap",
            "view_mode": "list,pivot,graph,form",
            "views": [(self.env.ref("mirabilenet_fibra.view_mirabilenet_fiber_nap_list").id,
                       "list"),
                      (self.env.ref("mirabilenet_fibra.view_mirabilenet_fiber_nap_pivot").id,
                       "pivot"),
                      (self.env.ref("mirabilenet_fibra.view_mirabilenet_fiber_nap_graph").id,
                       "graph"),
                      (False, "form")],
            "domain": domain,
            "context": {"group_by": ["neighborhood"]},
            "help": _("<p>No hay zonas con ocupación por debajo del %s %%, o las NAP aún no "
                      "tienen la cantidad de puertos definida.</p>", int(threshold)),
        }

    # ------------------------------------------------------------------
    # Mapa
    # ------------------------------------------------------------------
    def _map_values(self):
        return [{
            "id": nap.id,
            "code": nap.code,
            "name": nap.name or "",
            "branch_line": nap.branch_line or "",
            "neighborhood": nap.neighborhood or "",
            "state": nap.state,
            "state_label": dict(NAP_STATES).get(nap.state),
            "lat": nap.latitude,
            "lon": nap.longitude,
            "port_count": nap.port_count,
            "ports_free": nap.ports_free,
            "ports_used": nap.ports_used,
            "ports_damaged": nap.ports_damaged,
            "needs_review": nap.needs_review,
            "status": geo.nap_marker_status(nap.state, nap.port_count, nap.ports_free),
        } for nap in self if nap.latitude or nap.longitude]

    @api.model
    def get_fiber_map_data(self):
        """Datos del mapa con los permisos del usuario (sin sudo)."""
        naps = self.search([])
        segments = self.env["mirabilenet.fiber.segment"].search([])
        ports = self.env["mirabilenet.fiber.port"].search(
            [("service_id", "!=", False), ("nap_id", "in", naps.ids)])
        customers = []
        for port in ports:
            partner = port.partner_id
            if not (partner.partner_latitude or partner.partner_longitude):
                continue
            customers.append({
                "id": partner.id,
                "service_id": port.service_id.id,
                "name": partner.display_name,
                "phone": partner.phone or "",
                "lat": partner.partner_latitude,
                "lon": partner.partner_longitude,
                "nap_id": port.nap_id.id,
                "nap_code": port.nap_id.code,
                "port": port.number,
            })
        nap_values = naps._map_values()
        return {
            "naps": nap_values,
            "missing_position": len(naps) - len(nap_values),
            "segments": segments._map_values(),
            "customers": customers,
            "warnings": self._map_warnings(naps, segments),
            "can_move": self.env.user.has_group(FIBER_MANAGER),
            "segment_colors": geo.DEFAULT_SEGMENT_COLORS,
        }

    @api.model
    def _map_warnings(self, naps, segments):
        """Avisos de datos: lo marcado «revisar en campo» y lo que falta cargar."""
        warnings = []
        for nap in naps:
            for text in (nap.review_note or "").splitlines() if nap.needs_review else []:
                warnings.append({"model": "nap", "id": nap.id, "code": nap.code,
                                 "text": text, "kind": "revisar"})
            if not nap.port_count:
                warnings.append({"model": "nap", "id": nap.id, "code": nap.code,
                                 "text": _("Falta definir cantidad de puertos"),
                                 "kind": "puertos"})
            if not (nap.latitude or nap.longitude):
                warnings.append({"model": "nap", "id": nap.id, "code": nap.code,
                                 "text": _("Sin coordenadas: no aparece en el mapa"),
                                 "kind": "posicion"})
        for segment in segments:
            for text in (segment.review_note or "").splitlines() if segment.needs_review else []:
                warnings.append({"model": "segment", "id": segment.id, "code": segment.code,
                                 "text": text, "kind": "revisar"})
            if not segment.has_geometry:
                warnings.append({"model": "segment", "id": segment.id, "code": segment.code,
                                 "text": _("Sin recorrido real: línea recta provisoria"),
                                 "kind": "geometria"})
        return warnings

    @api.model
    def move_nap_marker(self, nap_id, latitude, longitude):
        """Guarda la posición de un marcador arrastrado. Solo el gestor de fibra."""
        if not self.env.user.has_group(FIBER_MANAGER):
            raise AccessError(_("Solo el gestor de fibra puede mover las NAP del mapa."))
        nap = self.browse(int(nap_id)).exists()
        if not nap:
            raise UserError(_("La NAP ya no existe."))
        latitude, longitude = float(latitude), float(longitude)
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise UserError(_("Coordenadas fuera de rango."))
        nap.write({"latitude": latitude, "longitude": longitude})
        nap.message_post(body=_("Ubicación corregida desde el mapa: %(lat)s, %(lon)s",
                                lat=latitude, lon=longitude))
        return True
