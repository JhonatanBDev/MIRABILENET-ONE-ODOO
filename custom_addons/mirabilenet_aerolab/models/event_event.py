"""AeroLab con los Eventos de Odoo: cada curso es un evento, el precio es su entrada y la
inscripción es la del sitio web. Aquí solo va lo que Odoo no trae."""
from datetime import datetime, time, timedelta

from markupsafe import Markup, escape

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from ..aerolab import contenido_inicial as C


class EventEvent(models.Model):
    _name = "event.event"
    _inherit = ["event.event", "mirabilenet.region.scoped"]
    _region_path = ("mirabilenet_region_id",)

    mirabilenet_region_id = fields.Many2one(
        "mirabilenet.region", string="Región", index=True, ondelete="restrict",
        default=lambda self: self.env.user.mirabilenet_region_id)
    mirabilenet_date_confirmed = fields.Boolean(
        string="Fecha confirmada", copy=False,
        help="Odoo pide una fecha a todo evento. Mientras no esté confirmada, el curso no se "
             "publica: esa fecha no se inventa.")
    mirabilenet_missing = fields.Char(string="Falta para publicar",
                                      compute="_compute_mirabilenet_missing")

    @api.depends("mirabilenet_date_confirmed", "seats_limited", "seats_max",
                 "event_ticket_ids.price")
    def _compute_mirabilenet_missing(self):
        for event in self:
            event.mirabilenet_missing = ", ".join(event._mirabilenet_missing_to_publish())

    def _mirabilenet_missing_to_publish(self):
        """Un curso sin fecha, cupo o precio queda en preparación."""
        self.ensure_one()
        missing = []
        if not self.mirabilenet_date_confirmed:
            missing.append(_("fecha confirmada"))
        if not self.seats_limited or self.seats_max <= 0:
            missing.append(_("cupo"))
        if not any(price > 0 for price in self.event_ticket_ids.mapped("price")):
            missing.append(_("precio (una entrada con precio)"))
        return missing

    @api.constrains("website_published", "mirabilenet_date_confirmed", "seats_limited",
                    "seats_max", "event_ticket_ids")
    def _check_mirabilenet_publication(self):
        for event in self.filtered("website_published"):
            missing = event._mirabilenet_missing_to_publish()
            if missing:
                raise ValidationError(_(
                    "El curso «%(name)s» queda en preparación hasta tener: %(missing)s. "
                    "Esos datos no se inventan.", name=event.name, missing=", ".join(missing)))

    # ------------------------------------------------------------------
    @api.model
    def _mirabilenet_load_initial_courses(self):
        """Los cursos con los que nació AeroLab, sin publicar y sin fecha confirmada, cupo
        ni precio. Repetirlo no duplica."""
        env = self.sudo().env
        region = env["mirabilenet.region"].search([], order="wg_region_id", limit=1)
        start = datetime.combine(fields.Date.context_today(self) + timedelta(days=30), time(13))
        created = self.env["event.event"]
        for data in C.CURSOS:
            if env["event.event"].with_context(active_test=False).search_count(
                    [("name", "=", data["nombre"])]):
                continue
            tags = env.ref("mirabilenet_aerolab.tag_level_%s" % data["nivel"]) | env.ref(
                "mirabilenet_aerolab.tag_application_%s" % data["aplicacion"])
            body = Markup("<p>%s</p>") % data["resumen"]
            for title, key in (("Temario", "temario"), ("Requisitos", "requisitos"),
                               ("Incluye", "incluye")):
                items = [line.strip() for line in (data.get(key) or "").splitlines()
                         if line.strip()]
                if items:
                    body += Markup("<h3>%s</h3><ul>%s</ul>") % (title, Markup("").join(
                        Markup("<li>%s</li>") % escape(item) for item in items))
            created |= env["event.event"].create({
                "name": data["nombre"], "tag_ids": [(6, 0, tags.ids)],
                "description": body, "website_published": False,
                "mirabilenet_region_id": region.id, "date_begin": start,
                "date_end": start + timedelta(hours=4)})
        if created:
            self.env["mirabilenet.audit.log"]._log(
                "crear", "Cursos de partida de AeroLab cargados: %d" % len(created),
                region=region, payload={"cursos": created.ids})
        return created
