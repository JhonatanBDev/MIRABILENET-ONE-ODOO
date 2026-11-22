import re
import unicodedata

from odoo import api, models, _
from odoo.exceptions import AccessError

PUBLISHER = "mirabilenet_web.group_mirabilenet_web_publisher"
ICONS = [
    ("antena", "Antena"), ("fibra", "Fibra óptica"), ("camara", "Cámara"),
    ("empresa", "Empresa"), ("hogar", "Hogar"), ("mina", "Minería"),
    ("comunidad", "Comunidad"), ("soporte", "Soporte"), ("escudo", "Seguridad"),
    ("velocidad", "Velocidad"), ("herramienta", "Instalación"), ("personas", "Personas"),
    ("reloj", "Tiempo"), ("check", "Verificado"),
]
#: Icono de cada clave en la tipografía de iconos que trae el sitio web.
FA_ICONS = {"antena": "signal", "fibra": "bolt", "camara": "video-camera",
            "empresa": "building", "hogar": "home", "mina": "industry", "comunidad": "users",
            "soporte": "life-ring", "escudo": "shield", "velocidad": "tachometer",
            "herramienta": "wrench", "personas": "user", "reloj": "clock-o", "check": "check"}


def slugify(text, limit=60):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit]


class MirabilenetWebPublished(models.AbstractModel):
    """Contenido del sitio público. Lo publican gerencia y administración regional."""
    _name = "mirabilenet.web.published"
    _description = "MIRABILENET: contenido del sitio"

    def _fa_icon(self):
        self.ensure_one()
        return FA_ICONS.get(self.icon, "circle")

    def _require_publisher(self):
        if not self.env.su and not self.env.user.has_group(PUBLISHER):
            raise AccessError(_("Publicar en el sitio corresponde a gerencia y a la "
                                "administración regional."))

    @api.model_create_multi
    def create(self, vals_list):
        self._require_publisher()
        return super().create(vals_list)

    def write(self, vals):
        self._require_publisher()
        return super().write(vals)

    def unlink(self):
        self._require_publisher()
        return super().unlink()
