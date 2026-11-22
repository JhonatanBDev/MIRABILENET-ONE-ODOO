from odoo import api, fields, models

from ..fibra import geo


class MirabilenetFiberKmlImportLine(models.TransientModel):
    """Una fila de la tabla de coincidencias del KML."""
    _name = "mirabilenet.fiber.kml.import.line"
    _description = "MIRABILENET: coincidencia de un placemark KML"

    wizard_id = fields.Many2one("mirabilenet.fiber.kml.import", required=True,
                                ondelete="cascade")
    region_id = fields.Many2one(related="wizard_id.region_id")
    confirm = fields.Boolean(string="Aplicar")
    kind = fields.Selection([("line", "Recorrido"), ("point", "Punto")], string="Tipo",
                            required=True)
    kml_name = fields.Char(string="Nombre en el KML")
    kml_color = fields.Char(string="Color")
    points_json = fields.Text(string="Coordenadas")
    vertex_count = fields.Integer(string="Vértices")
    kml_length_m = fields.Float(string="Longitud KML (m)", digits=(12, 1))
    segment_id = fields.Many2one("mirabilenet.fiber.segment", string="Tramo",
                                 domain="[('region_id', '=', region_id)]")
    nap_id = fields.Many2one("mirabilenet.fiber.nap", string="NAP",
                             domain="[('region_id', '=', region_id)]")
    current_length_m = fields.Float(related="segment_id.length_m", string="Longitud cargada")
    match_quality = fields.Selection(
        [("exacta", "Exacta"), ("probable", "Dudosa"), ("ninguna", "Ninguna")],
        string="Coincidencia")
    match_note = fields.Char(string="Motivo")
    length_differs = fields.Boolean(string="Difiere > 10 %", compute="_compute_length_differs")

    @api.depends("kml_length_m", "segment_id.length_m")
    def _compute_length_differs(self):
        for line in self:
            line.length_differs = bool(line.segment_id) and geo.differs(
                line.segment_id.length_m, line.kml_length_m)
