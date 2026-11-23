import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# Valores del tema que el módulo deja puestos en cada sitio. Son los mismos que guarda el
# editor (Editar > Tema): se pueden cambiar después desde ahí sin tocar código.
MIRABILENET_THEME_VALUES = {
    "color-palettes-name": "'mirabilenet'",
    "btn-border-radius": "0.5rem",
    "btn-border-radius-sm": "0.375rem",
    "btn-border-radius-lg": "0.625rem",
    "input-border-radius": "0.5rem",
    "input-border-radius-sm": "0.375rem",
    "input-border-radius-lg": "0.625rem",
}
USER_VALUES_URL = "/website/static/src/scss/options/user_values.scss"


class Website(models.Model):
    _inherit = "website"

    @api.model
    def _mirabilenet_apply_theme(self):
        """Pone la paleta «mirabilenet» y las esquinas redondeadas en todos los sitios."""
        assets = self.env["website.assets"]
        for website in self.search([]):
            try:
                with self.env.cr.savepoint():
                    assets.with_context(website_id=website.id).make_scss_customization(
                        USER_VALUES_URL, dict(MIRABILENET_THEME_VALUES))
            except Exception:
                # Al instalar, otro módulo del sitio puede no estar cargado todavía: el
                # tema no debe frenar la instalación. Se elige luego en Editar > Tema.
                _logger.warning("No se pudo poner la paleta MIRABILENET en el sitio %s; "
                                "elegirla en Editar > Tema > Colores.", website.name,
                                exc_info=True)
