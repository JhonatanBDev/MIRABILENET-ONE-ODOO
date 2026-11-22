import re
import time

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from ..controllers.main import lines
from ..models.mirabilenet_web_legal import SITE_COOKIES


class WebCommon:

    @classmethod
    def _setup_web(cls):
        # Las pruebas parten de un sitio sin contenidos, esté como esté la base.
        for name in ("legal", "faq", "advantage", "service", "figure", "ally", "project",
                     "coverage"):
            cls.env["mirabilenet.web.%s" % name].with_context(active_test=False).search(
                []).unlink()
        Region = cls.env["mirabilenet.region"]
        cls.norte = Region.create({"code": "W-N", "name": "Norte web", "wg_region_id": 61})
        cls.sur = Region.create({"code": "W-S", "name": "Sur web", "wg_region_id": 62})
        cls.gerencia = cls._user("w_gerencia", "gerencia")
        cls.admin_n = cls._user("w_admin_n", "admin_regional", cls.norte)
        cls.vendedor_n = cls._user("w_vendedor_n", "vendedor", cls.norte)
        cls.vendedor_s = cls._user("w_vendedor_s", "vendedor", cls.sur)
        cls.tecnico_n = cls._user("w_tecnico_n", "tecnico", cls.norte)
        cls.settings = cls.env["mirabilenet.web.settings"]._load()
        cls.settings.write({"hero_title": "Internet *sin vueltas* <b>", "whatsapp": "59170000000",
                            "phone": "70000000"})
        Service = cls.env["mirabilenet.web.service"]
        cls.service = Service.create({"name": "Internet Rural Ñandú", "summary": "Enlaces",
                                      "benefits": "Soporte local\n\nInstalación", "featured": True,
                                      "description": "Primera línea\n\nSegunda línea"})
        cls.hidden_service = Service.create({"name": "Servicio oculto", "summary": "No sale",
                                             "active": False})
        cls.env["mirabilenet.web.coverage"].create([
            {"region_id": cls.norte.id, "name": "Localidad Uno", "state": "parcial"},
            {"region_id": cls.sur.id, "name": "Localidad Oculta", "active": False}])
        cls.project = cls.env["mirabilenet.web.project"].create(
            {"title": "Red comunal", "summary": "Veinte familias", "kind": "comunidad",
             "description": "Tendido de fibra\nen dos etapas"})
        cls.env["mirabilenet.web.faq"].create(
            {"question": "¿Hay contrato?", "answer": "Sí.\n\nUno por servicio.",
             "category": "pagos"})
        Plan = cls.env["product.template"]

        def plan(code, price, publish):
            return Plan.create({
                "name": code, "type": "service", "mirabilenet_is_plan": True,
                "mirabilenet_plan_code": code, "list_price": price,
                "mirabilenet_region_id": cls.norte.id, "mirabilenet_down_mbps": 20,
                "mirabilenet_up_mbps": 10, "mirabilenet_publish_web": publish})
        cls.plan_public = plan("W-PUBLICADO", 150, True)
        cls.plan_private = plan("W-RESERVADO", 90, False)
        cls.plan_free = plan("W-SINPRECIO", 0, True)

    @classmethod
    def _user(cls, login, role, region=None):
        user = new_test_user(cls.env, login, groups="base.group_user")
        user.write({"mirabilenet_role": role,
                    "mirabilenet_region_id": region.id if region else False})
        return user

    @staticmethod
    def _form(**changes):
        data = {"tipo": "cotizacion", "nombre": "Ana Flores", "telefono": "+591 70012345",
                "email": "", "localidad": "Zona Norte", "region": "", "servicio": "",
                "plan_interes": "", "mensaje": "Quiero internet", "origen": "/planes/",
                "ts": "%.0f" % (time.time() - 30), "acepta": "on"}
        data.update(changes)
        return data


@tagged("mirabilenet", "post_install", "-at_install")
class TestWebContent(WebCommon, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_web()

    def test_only_management_publishes(self):
        Service = self.env["mirabilenet.web.service"]
        for user in (self.vendedor_n, self.tecnico_n):
            with self.assertRaises(AccessError):
                Service.with_user(user).create({"name": "X", "summary": "Y"})
            with self.assertRaises(AccessError):
                self.service.with_user(user).write({"summary": "Z"})
            with self.assertRaises(AccessError):
                self.settings.with_user(user).write({"phone": "1"})
        created = Service.with_user(self.admin_n).create({"name": "Cámaras IP", "summary": "CCTV"})
        self.assertEqual(created.slug, "camaras-ip")
        self.settings.with_user(self.gerencia).write({"city": "Riberalta"})

    def test_slug_and_single_settings(self):
        self.assertEqual(self.service.slug, "internet-rural-nandu")
        self.assertEqual(self.project.slug, "red-comunal")
        with self.assertRaises(UserError):
            self.env["mirabilenet.web.settings"].create({})
        with self.assertRaises(UserError):
            self.settings.unlink()
        with self.assertRaises(ValidationError):
            self.settings.write({"whatsapp": "+591 700"})
        with self.assertRaises(ValidationError):
            self.settings.write({"facebook": "javascript:alert(1)"})

    def test_headline_escapes_what_the_panel_writes(self):
        self.assertEqual(str(self.settings._headline()),
                         'Internet <span class="resalte">sin vueltas</span> &lt;b&gt;')
        self.assertEqual(lines(" uno \n\n dos\n"), ["uno", "dos"])

    def test_legal_document_sections(self):
        document = self.env["mirabilenet.web.legal"].create({
            "kind": "privacidad", "title": "Aviso",
            "content": "Entrada\n# Datos\nUsamos su teléfono.\n- Nombre\n- <b>Teléfono</b>"})
        sections = document._sections()
        self.assertEqual([s["titulo"] for s in sections], ["", "Datos"])
        self.assertEqual(sections[1]["vinetas"], ["Nombre", "<b>Teléfono</b>"])
        with self.assertRaises(Exception):
            self.env["mirabilenet.web.legal"].create(
                {"kind": "privacidad", "title": "Otro", "content": "x"})
            self.env.flush_all()

    def test_coverage_is_published_per_region(self):
        Coverage = self.env["mirabilenet.web.coverage"]
        Coverage.with_user(self.admin_n).create({"region_id": self.norte.id, "name": "Mía"})
        with self.assertRaises(AccessError):
            Coverage.with_user(self.admin_n).create({"region_id": self.sur.id, "name": "Ajena"})
        mine = Coverage.with_user(self.admin_n).search([("name", "=", "Mía")])
        with self.assertRaises(AccessError):
            mine.write({"region_id": self.sur.id})

    def test_initial_content_loads_once_and_keeps_what_was_written(self):
        with self.assertRaises(AccessError):
            self.settings.with_user(self.vendedor_n)._load_initial_content()
        self.settings.write({"description": "Texto propio"})
        created = self.settings.with_user(self.gerencia)._load_initial_content()
        self.assertEqual(created, {"ventajas": 3, "servicios": 6, "preguntas": 12,
                                   "textos legales": 3})
        self.assertEqual(self.settings.description, "Texto propio")
        self.assertEqual(self.settings.hero_title, "Internet *sin vueltas* <b>")
        self.assertEqual(self.settings.sales_email, "ventas@mirabilenet.com")
        self.assertFalse(self.settings.address)
        cookies = self.env["mirabilenet.web.legal"].search([("kind", "=", "cookies")])
        self.assertNotIn("csrftoken", cookies.content)
        self.assertNotIn("/panel/", cookies.content)
        self.assertTrue(cookies._sections())
        self.assertFalse(self.env["mirabilenet.web.project"].search(
            [("id", "!=", self.project.id)]))
        self.assertFalse(self.env["mirabilenet.web.figure"].search([]))
        again = self.settings.with_user(self.gerencia)._load_initial_content()
        self.assertEqual(set(again.values()), {0})

    # -- Formulario -----------------------------------------------------
    def test_form_validation(self):
        Lead = self.env["crm.lead"]
        self.assertEqual(Lead._mirabilenet_validate_web_form(self._form())[1], {})
        bad = {
            "general": {"website": "http://spam"}, "nombre": {"nombre": "Al"},
            "telefono": {"telefono": "12345"}, "email": {"email": "sin arroba"},
            "mensaje": {"mensaje": "http://a http://b http://c"}, "acepta": {"acepta": ""},
            "ts": {"ts": "%.0f" % time.time()},
        }
        for name, changes in bad.items():
            errors = Lead._mirabilenet_validate_web_form(self._form(**changes))[1]
            self.assertIn(name, errors, changes)
        for stamp in ("", "abc", "%.0f" % (time.time() - 7 * 3600)):
            self.assertIn("ts", Lead._mirabilenet_validate_web_form(self._form(ts=stamp))[1])
        self.assertIn("nombre", Lead._mirabilenet_validate_web_form(
            self._form(nombre="Visite https://x.example"))[1])
        values = Lead._mirabilenet_validate_web_form(self._form(tipo="inventado"))[0]
        self.assertEqual(values["tipo"], "contacto")

    def _lead(self, **changes):
        Lead = self.env["crm.lead"]
        values, errors = Lead._mirabilenet_validate_web_form(self._form(**changes))
        self.assertFalse(errors)
        return Lead._mirabilenet_create_from_web(values, ip="203.0.113.9", user_agent="Prueba")

    def test_lead_is_created_without_a_customer(self):
        partners = self.env["res.partner"].search_count([])
        lead = self._lead(region=str(self.norte.id), servicio=str(self.service.id))
        self.assertEqual(lead.type, "lead")
        self.assertEqual(lead.mirabilenet_origin, "web:/planes/")
        self.assertEqual(lead.mirabilenet_region_id, self.norte)
        self.assertEqual(lead.mirabilenet_web_service_id, self.service)
        self.assertEqual(lead.mirabilenet_status, "nuevo")
        self.assertFalse(lead.partner_id)
        self.assertEqual(self.env["res.partner"].search_count([]), partners)
        log = self.env["mirabilenet.audit.log"].search(
            [("model", "=", "crm.lead"), ("res_id", "=", lead.id)])
        self.assertEqual(len(log), 1)
        # Una región o un servicio que no existen no rompen el envío.
        other = self._lead(region="999999", servicio="abc")
        self.assertFalse(other.mirabilenet_region_id)

    def test_rate_limit_per_connection(self):
        Lead = self.env["crm.lead"]
        for _ in range(4):
            self._lead()
        self.assertFalse(Lead._mirabilenet_too_many("203.0.113.9"))
        self._lead()
        self.assertTrue(Lead._mirabilenet_too_many("203.0.113.9"))
        self.assertFalse(Lead._mirabilenet_too_many("203.0.113.10"))

    def test_visitor_text_is_not_editable(self):
        lead = self._lead(region=str(self.norte.id)).with_user(self.vendedor_n)
        for name, value in (("description", "otra cosa"), ("phone", "70000001"),
                            ("contact_name", "Otro"), ("mirabilenet_origin", "web:/")):
            with self.assertRaises(UserError):
                lead.write({name: value})
        lead.write({"mirabilenet_internal_note": "Llamar por la tarde"})
        self.assertEqual(lead.mirabilenet_internal_note, "Llamar por la tarde")

    def test_leads_are_isolated_by_region(self):
        north = self._lead(region=str(self.norte.id))
        unassigned = self._lead()
        Lead = self.env["crm.lead"]
        seen = Lead.with_user(self.vendedor_s).search([("id", "in", (north | unassigned).ids)])
        self.assertEqual(seen, unassigned)
        with self.assertRaises(AccessError):
            north.with_user(self.vendedor_s).action_mirabilenet_contacted()
        self.assertEqual(
            Lead.with_user(self.gerencia).search_count([("id", "in", (north | unassigned).ids)]), 2)

    def test_conversion_to_prospect_is_a_person_decision(self):
        lead = self._lead(region=str(self.norte.id))
        with self.assertRaises(AccessError):
            lead.with_user(self.tecnico_n).action_mirabilenet_to_prospect()
        partner = lead.with_user(self.vendedor_n).action_mirabilenet_to_prospect()
        self.assertTrue(partner.mirabilenet_is_customer)
        self.assertEqual(partner.mirabilenet_state, "prospecto")
        self.assertEqual(partner.mirabilenet_region_id, self.norte)
        self.assertEqual(partner.user_id, self.vendedor_n)
        self.assertIn("Quiero internet", partner.comment)
        self.assertEqual(lead.mirabilenet_status, "convertido")
        again = lead.with_user(self.vendedor_n).action_mirabilenet_to_prospect()
        self.assertEqual(again, partner)
        lead.with_user(self.vendedor_n).action_mirabilenet_discard()
        self.assertEqual(lead.mirabilenet_status, "convertido")
        # Sin región de la consulta se usa la de quien convierte.
        loose = self._lead(nombre="Luis Rojas")
        self.assertEqual(loose.with_user(self.vendedor_s).action_mirabilenet_to_prospect()
                         .mirabilenet_region_id, self.sur)


@tagged("mirabilenet", "post_install", "-at_install")
class TestWebPages(WebCommon, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_web()

    def _get(self, path, status=200):
        response = self.url_open(path)
        self.assertEqual(response.status_code, status, path)
        return response

    # Las listas son bloques dinámicos: el navegador las pide a /website/snippet/filters.
    TEMPLATES = {
        "servicios": "mirabilenet_web.dynamic_filter_template_mirabilenet_web_service_cards",
        "planes": "mirabilenet_web.dynamic_filter_template_product_template_mn_plans",
        "cobertura": "mirabilenet_web.dynamic_filter_template_mirabilenet_web_coverage_cards",
        "proyectos": "mirabilenet_web.dynamic_filter_template_mirabilenet_web_project_cards",
        "preguntas": "mirabilenet_web.dynamic_filter_template_mirabilenet_web_faq_list",
    }

    def _dynamic(self, kind, limit=16):
        filter_id = self.make_jsonrpc_request("/mirabilenet/web/filtro", {"clave": kind})
        self.assertEqual(filter_id, self.env.ref("mirabilenet_web.mn_filter_%s" % kind).id)
        return "".join(self.make_jsonrpc_request("/website/snippet/filters", {
            "filter_id": filter_id, "template_key": self.TEMPLATES[kind], "limit": limit,
            "search_domain": []}))

    def test_pages_live_inside_the_odoo_website(self):
        home = self._get("/").text
        # Es una página del sitio web de Odoo: lleva su cabecera, su menú y sus recursos.
        self.assertIn("web.assets_frontend", home)
        for label in ("Servicios", "Planes", "Cobertura", "Proyectos", "Preguntas", "Contacto"):
            self.assertIn(label, home)
        self.assertIn('href="/servicios"', home)
        for kind in ("ventajas", "cifras", "servicios", "aliados", "planes", "cobertura",
                     "proyectos"):
            self.assertIn('data-mn-filter="%s"' % kind, home)
        for path, kind in (("/servicios", "servicios"), ("/planes", "planes"),
                           ("/cobertura", "cobertura"), ("/proyectos", "proyectos"),
                           ("/preguntas-frecuentes", "preguntas")):
            self.assertIn('data-mn-filter="%s"' % kind, self._get(path).text, path)
        # Lo que muestra cada bloque: solo lo publicado.
        services = self._dynamic("servicios")
        self.assertIn("Internet Rural Ñandú", services)
        self.assertIn('href="/servicios/internet-rural-nandu"', services)
        self.assertNotIn("Servicio oculto", services)
        coverage = self._dynamic("cobertura")
        for text in ("Localidad Uno", "Cobertura parcial", "Norte web"):
            self.assertIn(text, coverage)
        self.assertNotIn("Localidad Oculta", coverage)
        self.assertIn("Red comunal", self._dynamic("proyectos"))
        self.assertIn("Uno por servicio.", self._dynamic("preguntas"))
        self.assertFalse(self.make_jsonrpc_request("/mirabilenet/web/filtro",
                                                   {"clave": "res.users"}))
        for path, expected in (
                ("/servicios/internet-rural-nandu", "Segunda línea"),
                ("/servicios/internet-rural-nandu", "Soporte local"),
                ("/proyectos/red-comunal", "en dos etapas"),
                ("/contacto?tipo=cotizacion", 'name="tipo" value="cotizacion"'),
                ("/contacto?tipo=cotizacion&plan=W-PUBLICADO", 'value="W-PUBLICADO"'),
                ("/gracias?tipo=cotizacion", "factibilidad")):
            self.assertIn(expected, self._get(path).text, path)
        self._get("/servicios/servicio-oculto", 404)
        self._get("/proyectos/no-existe", 404)

    def test_pages_are_editable_odoo_blocks(self):
        """Toda la página es editable: secciones estáticas y bloques dinámicos que el editor
        mueve y estiliza. Nada del código queda dentro de #wrap, así que guardar desde el
        editor no congela ningún dato."""
        from lxml import etree
        website = self.env["website"].get_current_website()
        for key in ("page_home", "page_services", "page_plans", "page_coverage",
                    "page_projects", "page_faq"):
            view = self.env.ref("mirabilenet_web.%s" % key)
            wrap = etree.fromstring(view.arch_db).xpath("//div[@id='wrap']")[0]
            self.assertIn("oe_structure", wrap.get("class"), key)
            directives = [a for el in wrap.iter() for a in el.attrib if a.startswith("t-")]
            self.assertFalse(directives, key)
        home = self.env.ref("mirabilenet_web.page_home")
        home.with_context(website_id=website.id).save(
            '<div id="wrap" class="oe_structure oe_empty">'
            '<section class="s_text_block" data-snippet="s_text_block"><div class="container">'
            '<p>Portada escrita en el editor</p><a class="btn btn-primary" href="/planes">Ir</a>'
            '</div></section>'
            '<section class="s_mn_plans s_mn_dynamic s_dynamic" data-mn-filter="planes" '
            'data-template-key="%s" data-number-of-records="3">'
            '<div class="dynamic_snippet_template"/></section></div>' % self.TEMPLATES["planes"],
            xpath="//div[@id='wrap']")
        page = self._get("/").text
        self.assertIn("Portada escrita en el editor", page)
        self.assertIn('data-mn-filter="planes"', page)
        self.assertIn("W-PUBLICADO", self._dynamic("planes"))

    def test_blocks_are_in_the_editor_panel(self):
        panel = self.env.ref("mirabilenet_web.snippets")
        self.assertEqual(panel.inherit_id, self.env.ref("website.snippets"))
        for snippet in ("s_mn_services", "s_mn_plans", "s_mn_coverage", "s_mn_projects",
                        "s_mn_faq", "s_mn_advantages", "s_mn_figures", "s_mn_allies"):
            self.assertIn('t-snippet="mirabilenet_web.%s"' % snippet, panel.arch_db)
            block = self.env.ref("mirabilenet_web.%s" % snippet)
            self.assertIn("s_mn_dynamic", block.arch_db)

    def test_plans_follow_the_publication_rule(self):
        plans = self._dynamic("planes")
        self.assertIn("W-PUBLICADO", plans)
        self.assertNotIn("W-RESERVADO", plans)
        self.assertNotIn("W-SINPRECIO", plans)
        self.assertIn(">150<", plans.replace(" ", "").replace("\n", ""))
        self.assertIn("plan=W-PUBLICADO", plans)
        self.settings.show_prices = False
        self.assertNotIn(">150<", self._dynamic("planes").replace(" ", "").replace("\n", ""))

    def test_legal_pages_exist_only_when_loaded(self):
        for path in ("/privacidad", "/cookies", "/terminos"):
            self._get(path, 404)
        self.env["mirabilenet.web.legal"].create({
            "kind": "cookies", "title": "Política de cookies", "version": "2.1",
            "content": "# Qué usamos\nUna sola.\n- <b>negrita</b>"})
        page = self._get("/cookies").text
        self.assertIn("Qué usamos", page)
        self.assertIn("&lt;b&gt;negrita&lt;/b&gt;", page)
        self.assertIn("2.1", page)
        self.assertIn("session_id", page)
        self._get("/privacidad", 404)

    def test_cookies_are_declared(self):
        declared = {c["nombre"] for c in SITE_COOKIES}
        for path in ("/", "/servicios", "/planes", "/contacto"):
            self.assertLessEqual(set(self._get(path).cookies.keys()), declared, path)

    def _post(self, **changes):
        page = self._get("/contacto").text
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        return self.url_open("/contacto", data=dict(self._form(**changes), csrf_token=token),
                             allow_redirects=False)

    def test_contact_form_creates_a_lead(self):
        Lead = self.env["crm.lead"]
        domain = [("mirabilenet_origin", "=like", "web:%")]
        before = Lead.search_count(domain)
        response = self._post(region=str(self.norte.id))
        self.assertEqual(response.status_code, 303)
        self.assertIn("/gracias?tipo=cotizacion", response.headers["Location"])
        lead = Lead.search(domain, order="id desc", limit=1)
        self.assertEqual(Lead.search_count(domain), before + 1)
        self.assertEqual(lead.contact_name, "Ana Flores")
        self.assertEqual(lead.mirabilenet_region_id, self.norte)
        self.assertTrue(lead.sudo().mirabilenet_source_ip)

        rejected = self._post(website="http://spam.example", nombre="<script>alert(1)</script>")
        self.assertEqual(rejected.status_code, 200)
        self.assertIn("Revise los datos marcados", rejected.text)
        self.assertIn("&lt;script&gt;alert(1)", rejected.text)
        self.assertNotIn("<script>alert(1)", rejected.text)
        self.assertEqual(Lead.search_count(domain), before + 1)

        without_token = self.url_open("/contacto", data=self._form(), allow_redirects=False)
        self.assertEqual(without_token.status_code, 400)
        self.assertEqual(Lead.search_count(domain), before + 1)

    def test_sitemap_and_image(self):
        sitemap = self._get("/sitemap.xml").text
        self.assertIn("/servicios/internet-rural-nandu", sitemap)
        self.assertIn("/planes", sitemap)
        self.assertNotIn("servicio-oculto", sitemap)
        self._get("/mirabilenet/web/imagen/proyecto/%d/image" % self.project.id, 404)
        self._get("/mirabilenet/web/imagen/proyecto/%d/write_date" % self.project.id, 404)
        self._get("/mirabilenet/web/imagen/usuario/1/image_1920", 404)


@tagged("mirabilenet", "post_install", "-at_install")
class TestWebCoverageHook(WebCommon, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_web()

    def test_published_localities_reach_other_modules(self):
        found = self.env["mirabilenet.region"]._mirabilenet_coverage_localities()
        self.assertIn((self.norte, "Localidad Uno", "Cobertura parcial", ""), found)
        self.assertNotIn("Localidad Oculta", [name for _r, name, _s, _d in found])
        if "mirabilenet.n8n.api" in self.env:
            self.env["mirabilenet.zone"].create(
                [{"region_id": self.norte.id, "name": "localidad uno", "code": "W-Z1"},
                 {"region_id": self.norte.id, "name": "Zona Libre", "code": "W-Z2"}])
            Api = self.env["mirabilenet.n8n.api"]
            mine = [c for c in Api._coverage() if c["region"] == "Norte web"]
            self.assertEqual([(c["zona"], c["estado"]) for c in mine],
                             [("Localidad Uno", "Cobertura parcial"),
                              ("Zona Libre", "Cobertura disponible")])
            self.assertEqual(Api._region_by_locality("LOCALIDAD UNO"), self.norte)
