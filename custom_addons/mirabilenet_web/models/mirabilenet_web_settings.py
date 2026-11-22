import re

from markupsafe import Markup, escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from ..web import contenido_inicial as C

SETTINGS_TEXTS = {
    "description": ("Instalamos y mantenemos internet y videovigilancia para hogares, "
                    "empresas, comunidades y operaciones alejadas, con soporte tecnico local."),
    "sales_email": "ventas@mirabilenet.com", "support_email": "soporte@mirabilenet.com",
    "legal_notice": C.AVISO,
    "hero_title": "Conectividad confiable. *Seguridad* que se nota.",
    "hero_phrase": "Conectamos lo que importa",
    "band_title": "Tecnologia confiable, soporte humano.",
    "band_text": ("Combinamos equipamiento de marcas reconocidas con un equipo local que "
                  "responde cuando hace falta."),
}


class MirabilenetWebSettings(models.Model):
    """Identidad y datos de contacto del sitio. Un solo registro."""
    _name = "mirabilenet.web.settings"
    _description = "MIRABILENET: configuración del sitio"
    _inherit = ["mirabilenet.web.published"]
    _rec_name = "trade_name"

    trade_name = fields.Char(string="Nombre comercial", default="MIRABILENET", required=True)
    slogan = fields.Char(
        string="Lema", required=True,
        default="Internet y videovigilancia para hogares, empresas y comunidades")
    description = fields.Text(string="Descripción corta",
                              help="Aparece en la portada y en los buscadores.")
    hero_title = fields.Char(
        string="Titular de la portada",
        help="Lo que ponga *entre asteriscos* sale en el azul de la marca. Vacío usa el lema.")
    hero_image = fields.Image(string="Imagen de la portada",
                              help="Sin imagen se muestra el logotipo animado.")
    hero_phrase = fields.Char(string="Frase sobre la imagen")
    band_title = fields.Char(string="Título de la banda de tecnologías")
    band_text = fields.Char(string="Texto de la banda de tecnologías")
    phone = fields.Char(string="Teléfono")
    whatsapp = fields.Char(string="WhatsApp",
                           help="Formato internacional sin signos, por ejemplo 59170000000.")
    sales_email = fields.Char(string="Correo de ventas")
    support_email = fields.Char(string="Correo de soporte")
    address = fields.Char(string="Dirección")
    city = fields.Char(string="Ciudad")
    schedule = fields.Char(string="Horario de atención")
    facebook = fields.Char(string="Facebook")
    instagram = fields.Char(string="Instagram")
    tiktok = fields.Char(string="TikTok")
    show_plans_home = fields.Boolean(string="Mostrar los planes en la portada", default=True)
    show_prices = fields.Boolean(
        string="Mostrar precios en la web", default=True,
        help="Si se desactiva, la página de planes invita a cotizar sin precios.")
    legal_notice = fields.Text(string="Aviso de privacidad (texto simple)")
    missing_data = fields.Char(string="Datos de contacto sin llenar",
                               compute="_compute_missing_data")

    @api.model
    def _load(self):
        settings = self.sudo().search([], limit=1, order="id")
        return settings or self.sudo().create({})

    @api.model_create_multi
    def create(self, vals_list):
        if self.sudo().search_count([]):
            raise UserError(_("La configuración del sitio es un solo registro."))
        return super().create(vals_list)

    def unlink(self):
        raise UserError(_("La configuración del sitio no se elimina."))

    @api.constrains("whatsapp", "facebook", "instagram", "tiktok")
    def _check_contact(self):
        for settings in self:
            if settings.whatsapp and not settings.whatsapp.isdigit():
                raise ValidationError(_("El WhatsApp va solo con dígitos, sin + ni espacios."))
            for link in (settings.facebook, settings.instagram, settings.tiktok):
                if link and not link.startswith("https://"):
                    raise ValidationError(_("Los enlaces a redes deben empezar con https://"))

    @api.depends("phone", "whatsapp", "address", "city", "schedule")
    def _compute_missing_data(self):
        labels = {"phone": "teléfono", "whatsapp": "WhatsApp", "address": "dirección",
                  "city": "ciudad", "schedule": "horario"}
        for settings in self:
            settings.missing_data = ", ".join(
                label for name, label in labels.items() if not settings[name])

    def _headline(self):
        """El titular con el resalte resuelto. Se escapa primero y se marca después: lo
        único que llega al HTML son las etiquetas que pone esta función."""
        self.ensure_one()
        return Markup(re.sub(r"\*([^*]+)\*", r'<span class="resalte">\1</span>',
                             str(escape(self.hero_title or self.slogan))))

    def _load_initial_content(self):
        """Carga los textos con los que nació el sitio. Se puede repetir: no pisa nada de lo
        ya escrito ni duplica. No trae datos de contacto, cifras ni proyectos."""
        self._require_publisher()
        env = self.sudo().env
        settings = self._load()
        settings.write({name: text for name, text in SETTINGS_TEXTS.items()
                        if not settings[name]})
        created = {"ventajas": 0, "servicios": 0, "preguntas": 0, "textos legales": 0}

        Advantage = env["mirabilenet.web.advantage"].with_context(active_test=False)
        for data in C.VENTAJAS:
            if not Advantage.search_count([("title", "=", data["titulo"])]):
                Advantage.create({"icon": data["icono"], "title": data["titulo"],
                                  "detail": data["detalle"], "sequence": data["orden"]})
                created["ventajas"] += 1

        Service = env["mirabilenet.web.service"].with_context(active_test=False)
        for data in C.SERVICIOS:
            if not Service.search_count([("slug", "=", data["slug"])]):
                Service.create({
                    "slug": data["slug"], "name": data["nombre"], "icon": data["icono"],
                    "summary": data["resumen"], "description": data["descripcion"],
                    "benefits": data["beneficios"], "featured": data.get("destacado", False),
                    "sequence": data["orden"]})
                created["servicios"] += 1

        Faq = env["mirabilenet.web.faq"].with_context(active_test=False)
        for sequence, (category, question, answer) in enumerate(C.PREGUNTAS, start=1):
            if not Faq.search_count([("question", "=", question)]):
                Faq.create({"category": category, "question": question, "answer": answer,
                            "sequence": sequence})
                created["preguntas"] += 1

        Legal = env["mirabilenet.web.legal"]
        for kind, title, summary, content in C.DOCUMENTOS:
            if not Legal.search_count([("kind", "=", kind)]):
                Legal.create({"kind": kind, "title": title, "summary": summary,
                              "content": content, "version": "1.0",
                              "valid_from": fields.Date.context_today(self)})
                created["textos legales"] += 1
        self.env["mirabilenet.audit.log"]._log(
            "crear", "Contenido inicial del sitio cargado", record=settings, payload=created)
        return created

    def action_load_initial_content(self):
        created = self._load_initial_content()
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Contenido inicial"), "sticky": False, "type": "success",
            "message": ", ".join("%s: %d" % item for item in created.items()),
            "next": {"type": "ir.actions.act_window_close"}}}
