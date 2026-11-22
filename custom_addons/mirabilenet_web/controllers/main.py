import time

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

from odoo.addons.website.controllers.main import Website

from ..models.mirabilenet_web_coverage import COVERAGE_STATES
from ..models.mirabilenet_web_legal import PANEL_COOKIES, SITE_COOKIES
from ..models.mirabilenet_web_project import PROJECT_KINDS
from ..models.website_snippet_filter import SOURCES

IMAGES = {"sitio": ("mirabilenet.web.settings", "hero_image"),
          "proyecto": ("mirabilenet.web.project", "image")}
FORM_FIELDS = ("tipo", "nombre", "telefono", "email", "localidad", "region", "servicio",
               "plan_interes", "mensaje")


def lines(text):
    """Texto simple partido en líneas con contenido."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


class MirabilenetWebsite(Website):
    """Las páginas de MIRABILENET dentro del sitio web de Odoo. Todo se lee con privilegios
    y solo sale lo publicado."""

    # ------------------------------------------------------------------
    def _mn_values(self, **extra):
        env = request.env
        values = {
            "sitio": env["mirabilenet.web.settings"]._load(), "lines": lines,
            "coverage_labels": dict(COVERAGE_STATES), "project_labels": dict(PROJECT_KINDS),
        }
        values.update(extra)
        return values

    def _mn_form(self, kind="contacto", values=None, errors=None, **initial):
        env = request.env
        data = dict.fromkeys(FORM_FIELDS, "")
        data.update(tipo=kind, acepta=False, **{k: str(v) for k, v in initial.items()})
        data.update(values or {})
        data["ts"] = "%.0f" % time.time()
        return {
            "values": data, "errors": errors or {},
            "regions": env["mirabilenet.region"].sudo().search([], order="name"),
            "services": env["mirabilenet.web.service"].sudo().search([]),
            "origin": request.httprequest.path,
        }

    # ------------------------------------------------------------------
    # Las páginas con listas son páginas editables del sitio: las listas son bloques dinámicos
    # que el navegador llena con /website/snippet/filters.
    @http.route()
    def index(self, **kw):
        return request.render("mirabilenet_web.page_home", self._mn_values())

    @http.route("/mirabilenet/web/filtro", type="jsonrpc", auth="public", website=True,
                readonly=True)
    def mn_filter_id(self, clave=None, **kw):
        """El número del filtro de un bloque dinámico de MIRABILENET («servicios», «planes»...)."""
        if clave not in SOURCES:
            return False
        record = request.env.ref("mirabilenet_web.mn_filter_%s" % clave, raise_if_not_found=False)
        return record.id if record else False

    @http.route("/servicios", type="http", auth="public", website=True, sitemap=True)
    def mn_services(self, **kw):
        return request.render("mirabilenet_web.page_services", self._mn_values())

    def _sitemap_services(env, rule, qs):
        for service in env["mirabilenet.web.service"].sudo().search([]):
            yield {"loc": "/servicios/%s" % service.slug}

    @http.route("/servicios/<string:slug>", type="http", auth="public", website=True,
                sitemap=_sitemap_services)
    def mn_service(self, slug, **kw):
        Service = request.env["mirabilenet.web.service"].sudo()
        service = Service.search([("slug", "=", slug)], limit=1)
        if not service:
            raise NotFound()
        return request.render("mirabilenet_web.page_service", self._mn_values(
            servicio=service, otros=Service.search([("id", "!=", service.id)], limit=3),
            form=self._mn_form("cotizacion", servicio=service.id)))

    @http.route("/planes", type="http", auth="public", website=True, sitemap=True)
    def mn_plans(self, **kw):
        return request.render("mirabilenet_web.page_plans", self._mn_values())

    @http.route("/cobertura", type="http", auth="public", website=True, sitemap=True)
    def mn_coverage(self, **kw):
        return request.render("mirabilenet_web.page_coverage", self._mn_values())

    @http.route("/proyectos", type="http", auth="public", website=True, sitemap=True)
    def mn_projects(self, **kw):
        return request.render("mirabilenet_web.page_projects", self._mn_values())

    def _sitemap_projects(env, rule, qs):
        for project in env["mirabilenet.web.project"].sudo().search([]):
            yield {"loc": "/proyectos/%s" % project.slug}

    @http.route("/proyectos/<string:slug>", type="http", auth="public", website=True,
                sitemap=_sitemap_projects)
    def mn_project(self, slug, **kw):
        Project = request.env["mirabilenet.web.project"].sudo()
        project = Project.search([("slug", "=", slug)], limit=1)
        if not project:
            raise NotFound()
        return request.render("mirabilenet_web.page_project", self._mn_values(
            proyecto=project, otros=Project.search([("id", "!=", project.id)], limit=3)))

    @http.route("/preguntas-frecuentes", type="http", auth="public", website=True, sitemap=True)
    def mn_faq(self, **kw):
        return request.render("mirabilenet_web.page_faq", self._mn_values())

    # ------------------------------------------------------------------
    @http.route("/contacto", type="http", auth="public", website=True, sitemap=True,
                methods=["GET", "POST"])
    def mn_contact(self, **post):
        Lead = request.env["crm.lead"]
        kinds = dict(Lead._fields["mirabilenet_kind"].selection)
        if request.httprequest.method != "POST":
            kind = post.get("tipo") if post.get("tipo") in kinds else "contacto"
            return request.render("mirabilenet_web.page_contact", self._mn_values(
                tipo=kind, aviso="",
                form=self._mn_form(kind, plan_interes=(post.get("plan") or "")[:80])))
        ip = request.httprequest.remote_addr or ""
        values, errors = Lead._mirabilenet_validate_web_form(post)
        if Lead._mirabilenet_too_many(ip):
            notice = ("Ya recibimos varias consultas desde esta conexión. "
                      "Escríbanos por WhatsApp o intente más tarde.")
        elif errors:
            notice = "Revise los datos marcados y vuelva a enviar."
        else:
            Lead._mirabilenet_create_from_web(
                values, ip=ip, user_agent=request.httprequest.headers.get("User-Agent", ""))
            return request.redirect("/gracias?tipo=%s" % values["tipo"], code=303)
        return request.render("mirabilenet_web.page_contact", self._mn_values(
            tipo=values["tipo"], aviso=notice,
            form=self._mn_form(values["tipo"], values=values, errors=errors)))

    @http.route("/gracias", type="http", auth="public", website=True, sitemap=False)
    def mn_thanks(self, tipo="contacto", **kw):
        return request.render("mirabilenet_web.page_thanks", self._mn_values(tipo=tipo))

    # ------------------------------------------------------------------
    def _mn_legal(self, kind):
        """Sin documento cargado se responde 404: un aviso legal vacío publicado es peor
        que uno que no existe."""
        document = request.env["mirabilenet.web.legal"].sudo().search(
            [("kind", "=", kind)], limit=1)
        if not document:
            raise NotFound()
        cookies = kind == "cookies"
        return request.render("mirabilenet_web.page_legal", self._mn_values(
            documento=document, cookies_sitio=SITE_COOKIES if cookies else [],
            cookies_panel=PANEL_COOKIES if cookies else []))

    @http.route("/privacidad", type="http", auth="public", website=True, sitemap=True)
    def mn_privacy(self, **kw):
        return self._mn_legal("privacidad")

    @http.route("/cookies", type="http", auth="public", website=True, sitemap=True)
    def mn_cookies(self, **kw):
        return self._mn_legal("cookies")

    @http.route("/terminos", type="http", auth="public", website=True, sitemap=True)
    def mn_terms(self, **kw):
        return self._mn_legal("terminos")

    @http.route("/mirabilenet/web/imagen/<string:kind>/<int:record_id>/<string:field>",
                type="http", auth="public", methods=["GET"])
    def mn_image(self, kind, record_id, field, **kw):
        model, allowed = IMAGES.get(kind, (None, None))
        if not model or field != allowed:
            raise NotFound()
        record = request.env[model].sudo().search([("id", "=", record_id)], limit=1)
        if not record or not record[field]:
            raise NotFound()
        return request.env["ir.binary"]._get_image_stream_from(record, field).get_response()
