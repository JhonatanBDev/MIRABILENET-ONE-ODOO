from odoo import models

from .mirabilenet_web_coverage import COVERAGE_STATES
from .mirabilenet_web_faq import FAQ_CATEGORIES
from .mirabilenet_web_project import PROJECT_KINDS

#: Cada bloque dinámico de MIRABILENET: modelo, condición y orden. Solo sale lo publicado
#: (activo); los planes, además, con la regla de publicación de los planes.
SOURCES = {
    "servicios": ("mirabilenet.web.service", [], "featured desc, sequence, name"),
    "planes": ("product.template", [("mirabilenet_published", "=", True)], "list_price, id"),
    "cobertura": ("mirabilenet.web.coverage", [], "region_id, sequence, name"),
    "proyectos": ("mirabilenet.web.project", [], "sequence, date desc, id desc"),
    "preguntas": ("mirabilenet.web.faq", [], "sequence, id"),
    "ventajas": ("mirabilenet.web.advantage", [], "sequence, id"),
    "cifras": ("mirabilenet.web.figure", [], "sequence, id"),
    "aliados": ("mirabilenet.web.ally", [], "sequence, id"),
}
BADGES = {"disponible": "text-bg-success", "parcial": "text-bg-warning"}


def _lines(text):
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


class WebsiteSnippetFilter(models.Model):
    _inherit = "website.snippet.filter"

    def _mirabilenet_records(self, kind):
        """Registros de un bloque dinámico de MIRABILENET, listos para su plantilla.

        La llama la acción de servidor de cada filtro. Lee con privilegios porque el visitante
        no tiene acceso a estos modelos, y por eso no acepta condiciones que vengan del
        navegador: solo sale lo que la condición de aquí deja salir.
        """
        dynamic_filter = self.env.context.get("dynamic_filter")
        model, domain, order = SOURCES[kind]
        limit = min(int(self.env.context.get("limit") or 16), 16)
        records = self.env[model].sudo().search(domain, order=order, limit=limit)
        values = dynamic_filter._filter_records_to_values(records)
        settings = self.env["mirabilenet.web.settings"].sudo()._load()
        for data in values:
            data.update(self._mirabilenet_extra(kind, data["_record"], settings))
        return values

    def _mirabilenet_extra(self, kind, record, settings):
        if kind == "servicios":
            return {"mn_icon": record._fa_icon(), "mn_url": "/servicios/%s" % record.slug}
        if kind == "planes":
            return {"mn_price": "%.0f" % record.list_price if settings.show_prices else "",
                    "mn_down": record.mirabilenet_down_mbps, "mn_up": record.mirabilenet_up_mbps,
                    "mn_tv": record.mirabilenet_includes_tv,
                    "mn_region": record.mirabilenet_region_id.name or "",
                    "mn_url": "/contacto?tipo=cotizacion&plan=%s" % record.mirabilenet_plan_code}
        if kind == "cobertura":
            return {"mn_state": dict(COVERAGE_STATES).get(record.state, ""),
                    "mn_badge": BADGES.get(record.state, "text-bg-secondary"),
                    "mn_region": record.region_id.name}
        if kind == "proyectos":
            place = ", ".join(x for x in (record.location, record.date and record.date.strftime(
                "%m/%Y")) if x)
            return {"mn_kind": dict(PROJECT_KINDS).get(record.kind, ""),
                    "mn_url": "/proyectos/%s" % record.slug, "mn_place": place,
                    "mn_image": "/mirabilenet/web/imagen/proyecto/%s/image" % record.id
                    if record.image else ""}
        if kind == "preguntas":
            return {"mn_category": dict(FAQ_CATEGORIES).get(record.category, ""),
                    "mn_answer": _lines(record.answer)}
        if kind in ("ventajas", "cifras"):
            return {"mn_icon": record._fa_icon()}
        return {}
