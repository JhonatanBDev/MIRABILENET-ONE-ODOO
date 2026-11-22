import base64
import hashlib

from odoo import api, fields, models, _

from ..siat import errors as siat_errors


class MiraSiatXsd(models.Model):
    """XSD oficial versionado. Cada factura registra con qué versión se validó."""
    _name = "mira.siat.xsd"
    _description = "Mira_Sale SIAT: esquema XSD"
    _order = "sector_code, modality, id desc"

    name = fields.Char(string="Nombre", required=True)
    sector_code = fields.Integer(string="Documento sector", required=True, default=1)
    modality = fields.Selection(
        [("2", "Computarizada en Línea"), ("1", "Electrónica en Línea")],
        string="Modalidad", required=True, default="2")
    file = fields.Binary(string="Archivo XSD", required=True, attachment=False)
    filename = fields.Char(string="Nombre de archivo")
    sha256 = fields.Char(string="Huella (SHA-256)", compute="_compute_sha256", store=True)
    version_note = fields.Char(string="Versión / fecha de descarga")
    active = fields.Boolean(default=True)

    @api.depends("file")
    def _compute_sha256(self):
        for xsd in self:
            raw = base64.b64decode(xsd.with_context(bin_size=False).file or b"")
            xsd.sha256 = hashlib.sha256(raw).hexdigest() if raw else False

    @api.model
    def _get(self, sector_code, modality):
        xsd = self.sudo().search(
            [("sector_code", "=", sector_code), ("modality", "=", str(modality))], limit=1)
        if not xsd:
            raise siat_errors.SiatError(
                siat_errors.XSD,
                _("No hay un XSD oficial cargado para el sector %(sector)s en esa "
                  "modalidad. No se envía ningún documento sin validación local.",
                  sector=sector_code))
        return xsd

    def _content(self):
        self.ensure_one()
        return base64.b64decode(self.with_context(bin_size=False).file)
