from odoo import fields, models

LEGAL_KINDS = [("privacidad", "Aviso de privacidad"), ("cookies", "Política de cookies"),
               ("terminos", "Condiciones de uso")]
#: Las cookies que pone el sitio público. La página de cookies se dibuja desde aquí, y una
#: prueba las compara con lo que el sitio manda de verdad.
SITE_COOKIES = [{
    "nombre": "session_id", "titular": "MIRABILENET (propia)",
    "finalidad": ("Impedir que un tercero envíe el formulario de contacto en su nombre desde "
                  "otro sitio. Sin ella el formulario no funciona."),
    "categoria": "Estrictamente necesaria", "duracion": "Hasta 3 meses",
}, {
    "nombre": "frontend_lang", "titular": "MIRABILENET (propia)",
    "finalidad": "Recordar el idioma en que se muestra el sitio.",
    "categoria": "Preferencia", "duracion": "1 año",
}]
#: Las que se agregan solo al entrar al sistema de gestión, no al navegar el sitio.
PANEL_COOKIES = [
    {"nombre": "session_id", "titular": "MIRABILENET (propia)",
     "finalidad": ("Mantener la sesión de quien administra la plataforma. Es httpOnly: el "
                   "JavaScript de la página no puede leerla."),
     "categoria": "Estrictamente necesaria", "duracion": "Hasta 3 meses"},
    {"nombre": "cids / frontend_lang", "titular": "MIRABILENET (propia)",
     "finalidad": "Recordar la empresa y el idioma elegidos en el sistema de gestión.",
     "categoria": "Preferencia", "duracion": "1 año"},
]


class MirabilenetWebLegal(models.Model):
    """Aviso de privacidad, política de cookies y condiciones de uso. Quedan fechados: ante
    un reclamo hay que poder decir qué texto estaba publicado."""
    _name = "mirabilenet.web.legal"
    _description = "MIRABILENET: documento legal"
    _inherit = ["mirabilenet.web.published"]
    _order = "kind"
    _rec_name = "title"

    kind = fields.Selection(LEGAL_KINDS, string="Documento", required=True)
    title = fields.Char(string="Título", required=True, size=120)
    summary = fields.Char(string="Resumen", size=300)
    content = fields.Text(
        string="Contenido", required=True,
        help="Una línea que empieza con # es un subtítulo. El resto son párrafos; las líneas "
             "que empiezan con - son viñetas. No se admite HTML.")
    version = fields.Char(string="Versión", default="1.0", required=True, size=20)
    valid_from = fields.Date(string="Vigente desde", required=True,
                             default=fields.Date.context_today)

    _kind_uniq = models.Constraint("unique(kind)", "Ese documento ya existe: edítelo.")

    def _sections(self):
        """Parte el contenido en subtítulo, párrafos y viñetas, sin permitir HTML."""
        self.ensure_one()
        sections, current = [], None
        for line in (self.content or "").split("\n"):
            text = line.strip()
            if not text:
                continue
            if text.startswith("#"):
                current = {"titulo": text.lstrip("#").strip(), "parrafos": [], "vinetas": []}
                sections.append(current)
                continue
            if current is None:
                current = {"titulo": "", "parrafos": [], "vinetas": []}
                sections.append(current)
            if text.startswith("- "):
                current["vinetas"].append(text[2:].strip())
            else:
                current["parrafos"].append(text)
        return sections
