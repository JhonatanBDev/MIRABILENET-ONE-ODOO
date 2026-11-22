"""Genera los bloques dinámicos de MIRABILENET y las páginas editables del sitio.

Una sola definición por lista: el mismo bloque se usa en el panel del editor y en las páginas.
"""
import os
import re
from xml.sax.saxutils import escape as x

MOD = r'C:\ING.SISTEMAS\SISTEMAS_Y_PROYECTOS\odoo\custom_addons\mirabilenet_web'

# clave: (bloque, nombre, modelo, sufijo de plantilla, campos, título, bajada, enlace, texto
#         del enlace, columnas, clases extra)
KINDS = {
    "servicios": ("s_mn_services", "Servicios", "mirabilenet.web.service", "cards",
                  "name,summary", "Servicios",
                  "Un solo proveedor para la conexión, las cámaras y el soporte.",
                  "/servicios", "Ver todos los servicios", "col-12 col-md-6 col-lg-3", "g-4"),
    "planes": ("s_mn_plans", "Planes de internet", "product.template", "mn_plans", "name",
               "Planes de internet",
               "Precios mensuales en bolivianos. La instalación se cotiza aparte.",
               "/planes", "Ver todos los planes", "col-12 col-md-6 col-lg-4", "g-4"),
    "cobertura": ("s_mn_coverage", "Cobertura", "mirabilenet.web.coverage", "cards",
                  "name,detail", "Dónde damos servicio",
                  "Revisamos cada solicitud caso por caso.", "/cobertura",
                  "Ver la cobertura completa", "col-6 col-md-4 col-lg-3", "g-3"),
    "proyectos": ("s_mn_projects", "Proyectos", "mirabilenet.web.project", "cards",
                  "title,summary", "Trabajos realizados",
                  "Redes que instalamos y mantenemos.", "/proyectos",
                  "Ver todos los proyectos", "col-12 col-md-6 col-lg-4", "g-4"),
    "preguntas": ("s_mn_faq", "Preguntas frecuentes", "mirabilenet.web.faq", "list",
                  "question", "Preguntas frecuentes",
                  "Si no encuentra su respuesta, escríbanos.", "/preguntas-frecuentes",
                  "Ver todas las preguntas", "col-12", "g-2"),
    "ventajas": ("s_mn_advantages", "Ventajas", "mirabilenet.web.advantage", "list",
                 "title,detail", "Por qué elegirnos", "", "", "", "col-12 col-md-4", "g-4"),
    "cifras": ("s_mn_figures", "Cifras", "mirabilenet.web.figure", "list", "value,label",
               "En números", "", "", "", "col-6 col-md-3", "g-4"),
    "aliados": ("s_mn_allies", "Tecnologías y aliados", "mirabilenet.web.ally", "list",
                "name,detail", "Tecnologías y aliados", "", "", "", "col-auto", "g-2"),
}

# Plantilla de cada elemento de la lista (una raíz por registro). Se usa data.get(): en el
# editor, sin registros, Odoo muestra datos de muestra que no traen los valores propios.
ITEM = {
    "servicios": """
            <div class="card h-100 border-0 shadow-sm">
                <div class="card-body">
                    <i t-attf-class="fa fa-2x text-primary mb-3 fa-#{data.get('mn_icon', 'circle')}"/>
                    <h3 class="h5" t-out="data.get('name')"/>
                    <p class="text-muted" t-out="data.get('summary')"/>
                    <a t-if="data.get('mn_url')" t-att-href="data['mn_url']">Ver detalle <i class="fa fa-long-arrow-right"/></a>
                </div>
            </div>""",
    "planes": """
            <div t-attf-class="card h-100 shadow-sm text-center #{'border-primary' if data_index == 1 else ''}">
                <div class="card-body">
                    <span t-if="data_index == 1" class="badge text-bg-primary mb-2">Más contratado</span>
                    <h3 class="h5" t-out="data.get('name')"/>
                    <p t-if="data.get('mn_price')" class="display-6 mb-0">
                        <small class="h5">Bs</small> <span t-out="data['mn_price']"/>
                        <small class="h6 text-muted">/mes</small>
                    </p>
                    <p t-if="data.get('mn_down')" class="mt-3 mb-1"><strong t-out="data['mn_down']"/> Mbps de bajada</p>
                    <p t-if="data.get('mn_up')" class="mb-1"><strong t-out="data['mn_up']"/> Mbps de subida</p>
                    <p t-if="data.get('mn_tv')" class="mb-1">Incluye servicio de TV</p>
                    <p t-if="data.get('mn_region')" class="text-muted small" t-out="data['mn_region']"/>
                    <a t-att-href="data.get('mn_url', '/contacto?tipo=cotizacion')"
                       t-attf-class="btn mt-2 #{'btn-primary' if data_index == 1 else 'btn-outline-primary'}">Lo quiero</a>
                </div>
            </div>""",
    "cobertura": """
            <div class="card h-100">
                <div class="card-body">
                    <strong t-out="data.get('name')"/>
                    <span t-if="data.get('mn_state')" t-attf-class="badge ms-2 #{data.get('mn_badge', 'text-bg-secondary')}" t-out="data['mn_state']"/>
                    <div t-if="data.get('mn_region')" class="small text-primary mt-1" t-out="data['mn_region']"/>
                    <div t-if="data.get('detail')" class="text-muted small mt-1" t-out="data['detail']"/>
                </div>
            </div>""",
    "proyectos": """
            <div class="card h-100 shadow-sm">
                <img t-if="data.get('mn_image')" class="card-img-top" t-att-src="data['mn_image']" t-att-alt="data.get('title')"/>
                <div class="card-body">
                    <small t-if="data.get('mn_kind')" class="text-uppercase text-primary" t-out="data['mn_kind']"/>
                    <h3 class="h5 mt-1">
                        <a t-if="data.get('mn_url')" t-att-href="data['mn_url']" t-out="data.get('title')"/>
                        <t t-else="" t-out="data.get('title')"/>
                    </h3>
                    <p class="text-muted" t-out="data.get('summary')"/>
                    <small t-if="data.get('mn_place')" class="text-muted" t-out="data['mn_place']"/>
                </div>
            </div>""",
    "preguntas": """
            <details class="border rounded p-3 w-100">
                <summary class="fw-bold" t-out="data.get('question')"/>
                <small t-if="data.get('mn_category')" class="text-primary" t-out="data['mn_category']"/>
                <p t-foreach="data.get('mn_answer', [])" t-as="parrafo" class="mt-2 mb-0" t-out="parrafo"/>
            </details>""",
    "ventajas": """
            <div class="d-flex">
                <i t-attf-class="fa fa-lg text-primary me-3 mt-1 fa-#{data.get('mn_icon', 'check')}"/>
                <div>
                    <strong t-out="data.get('title')"/>
                    <div t-if="data.get('detail')" class="text-muted" t-out="data['detail']"/>
                </div>
            </div>""",
    "cifras": """
            <div class="text-center">
                <div class="h2 text-primary mb-0" t-out="data.get('value')"/>
                <div class="text-muted" t-out="data.get('label')"/>
            </div>""",
    "aliados": """
            <span class="badge text-bg-light border p-2">
                <t t-out="data.get('name')"/>
                <small t-if="data.get('detail')" class="text-muted"> · <t t-out="data['detail']"/></small>
            </span>""",
}


def template_key(kind):
    _snippet, _name, model, suffix = KINDS[kind][:4]
    return "mirabilenet_web.dynamic_filter_template_%s_%s" % (model.replace(".", "_"), suffix)


def block(kind, records, title=None, lead=None, link=True, bg=""):
    """Sección del bloque dinámico: HTML estático que el editor puede mover y estilizar."""
    (snippet, name, _model, _suffix, _fields, k_title, k_lead, url, url_text, cols,
     extra) = KINDS[kind]
    title = k_title if title is None else title
    lead = k_lead if lead is None else lead
    head = '<h2 class="h3">%s</h2>' % x(title)
    if lead:
        head += '\n                        <p class="lead">%s</p>' % x(lead)
    more = ""
    if link and url:
        more = ('\n                    <div>\n                        <a href="%s">%s<span '
                'class="fa fa-long-arrow-right ms-2"/></a>\n                    </div>' % (
                    url, x(url_text)))
    return """<section class="%(snippet)s s_mn_dynamic s_dynamic o_colored_level pt48 pb48%(bg)s" data-snippet="%(snippet)s" data-name="%(name)s" data-mn-filter="%(kind)s" data-template-key="%(tkey)s" data-number-of-records="%(records)s" data-column-classes="%(cols)s" data-extra-classes="%(extra)s">
        <div class="s_dynamic_snippet_container container">
            <div class="row s_nb_column_fixed">
                <section class="s_dynamic_snippet_title oe_unremovable oe_unmovable d-flex justify-content-between flex-column flex-md-row mb-lg-0 pb-3 pb-md-0 s_col_no_resize">
                    <div>
                        %(head)s
                    </div>%(more)s
                </section>
                <section class="s_dynamic_snippet_content oe_unremovable oe_unmovable o_not_editable col s_col_no_resize">
                    <div class="css_non_editable_mode_hidden">
                        <div class="missing_option_warning alert alert-info fade show d-none d-print-none rounded-0">Todavía no hay datos publicados: cárguelos en MIRABILENET &gt; Sitio web.</div>
                    </div>
                    <div class="dynamic_snippet_template"/>
                </section>
            </div>
        </div>
    </section>""" % dict(snippet=snippet, name=x(name + " (MIRABILENET)"), kind=kind,
                         tkey=template_key(kind), records=records, cols=cols, extra=extra,
                         head=head, more=more, bg=(" " + bg) if bg else "")


def title_section(overline, title, lead):
    return """<section class="s_title o_colored_level pt48 pb32 bg-100" data-snippet="s_title" data-name="Título">
        <div class="container text-center">
            <small class="text-uppercase text-primary fw-bold">%s</small>
            <h1 class="mt-2">%s</h1>
            <p class="lead text-muted">%s</p>
        </div>
    </section>""" % (x(overline), x(title), x(lead))


def cta(title, text, button, href):
    return """<section class="s_call_to_action o_colored_level pt48 pb48 bg-100" data-snippet="s_call_to_action" data-name="Llamada a la acción">
        <div class="container">
            <div class="row align-items-center">
                <div class="col-lg-9 pb16">
                    <h2 class="h3">%s</h2>
                    <p class="lead mb-0">%s</p>
                </div>
                <div class="col-lg-3 pb16 text-lg-end">
                    <a class="btn btn-primary btn-lg" href="%s">%s</a>
                </div>
            </div>
        </div>
    </section>""" % (x(title), x(text), x(href), x(button))


HERO = """<section class="s_text_block mn_hero o_colored_level pt72 pb72 bg-100" data-snippet="s_text_block" data-name="Portada">
        <div class="container">
            <div class="row align-items-center">
                <div class="col-lg-8">
                    <h1 class="display-4 fw-bold">Internet y videovigilancia para hogares, empresas y comunidades</h1>
                    <p class="lead text-muted">Conexión estable, instalación profesional y soporte local.</p>
                    <p>
                        <a class="btn btn-primary btn-lg me-2" href="/contacto?tipo=cotizacion">Solicitar cotización</a>
                        <a class="btn btn-outline-primary btn-lg" href="/planes">Ver planes</a>
                    </p>
                </div>
            </div>
        </div>
    </section>"""

CTA_HOME = cta("Hablemos", "Cuéntenos dónde está y qué necesita: le respondemos con una propuesta.",
               "Escríbanos", "/contacto?tipo=cotizacion")

PAGES = {
    "page_home": ("MIRABILENET: portada", "homepage", [
        HERO, block("ventajas", 6, title="Por qué elegirnos", link=False),
        block("cifras", 4, title="En números", link=False),
        block("servicios", 4), block("aliados", 16, link=False, bg="bg-100"),
        block("planes", 3), block("cobertura", 8, bg="bg-100"), block("proyectos", 3),
        CTA_HOME]),
    "page_services": ("MIRABILENET: servicios", None, [
        title_section("Servicios", "Todo lo que instalamos y mantenemos",
                      "Un solo proveedor para la conexión, las cámaras y el soporte. Sin "
                      "intermediarios."),
        block("servicios", 16, title="Nuestros servicios", lead="", link=False),
        cta("¿Necesita una cotización?", "Le respondemos con una propuesta para su caso.",
            "Pedir cotización", "/contacto?tipo=cotizacion")]),
    "page_plans": ("MIRABILENET: planes", None, [
        title_section("Planes", "Planes de internet",
                      "Precios mensuales en bolivianos. La instalación se cotiza aparte según "
                      "la distancia y el equipo."),
        block("planes", 16, title="Elija su plan", lead="", link=False),
        cta("Cada instalación es distinta", "Escríbanos y le respondemos con una propuesta.",
            "Pedir cotización", "/contacto?tipo=cotizacion")]),
    "page_coverage": ("MIRABILENET: cobertura", None, [
        title_section("Cobertura", "Dónde damos servicio",
                      "Revisamos cada solicitud caso por caso. Si su localidad no figura, "
                      "consúltenos igual."),
        block("cobertura", 16, title="Localidades", lead="", link=False),
        cta("¿No ve su zona?", "Consúltenos: evaluamos cada pedido.", "Consultar",
            "/contacto?tipo=factibilidad")]),
    "page_projects": ("MIRABILENET: proyectos", None, [
        title_section("Proyectos", "Trabajos realizados",
                      "Redes de comunidades, empresas e instituciones que instalamos y "
                      "mantenemos."),
        block("proyectos", 16, title="Proyectos", lead="", link=False),
        CTA_HOME]),
    "page_faq": ("MIRABILENET: preguntas frecuentes", None, [
        title_section("Ayuda", "Preguntas frecuentes",
                      "Si no encuentra su respuesta, escríbanos y le contestamos."),
        block("preguntas", 16, title="Preguntas", lead="", link=False),
        cta("¿Tiene otra pregunta?", "Escríbanos y le contestamos.", "Escribir",
            "/contacto")]),
}


def page(view_id):
    name, page_name, sections = PAGES[view_id]
    page_name_set = ('\n            <t t-set="pageName" t-value="\'%s\'"/>' % page_name
                     if page_name else "")
    body = "\n    ".join(sections)
    return """    <template id="%s" name="%s">
        <t t-call="website.layout">%s
            <div id="wrap" class="oe_structure oe_empty">
    %s
            </div>
        </t>
    </template>""" % (view_id, x(name), page_name_set, body)


def snippets_xml():
    out = ['<?xml version="1.0" encoding="utf-8"?>', "<odoo>",
           "    <!-- Generado por la herramienta del sitio: bloques dinámicos de MIRABILENET. -->"]
    for kind, spec in KINDS.items():
        snippet, name = spec[0], spec[1]
        out.append('    <template id="%s" name="%s (MIRABILENET)">\n    %s\n    </template>' % (
            snippet, x(name), block(kind, {"preguntas": 16, "cobertura": 16,
                                           "aliados": 16}.get(kind, 4))))
    for kind, spec in KINDS.items():
        tkey = template_key(kind).split(".", 1)[1]
        out.append(
            '    <template id="%s" name="%s">\n'
            '        <t t-foreach="records" t-as="data" data-column-classes="%s" '
            'data-extra-classes="%s">%s\n        </t>\n    </template>' % (
                tkey, x("MIRABILENET: " + spec[1]), spec[9], spec[10], ITEM[kind]))
    out.append('''    <template id="snippets" inherit_id="website.snippets" name="MIRABILENET: bloques">
        <xpath expr="//t[@id='installed_snippets_hook']" position="before">
            <t snippet-group="mirabilenet" t-snippet="website.s_snippet_group" string="MIRABILENET"
               t-thumbnail="/mirabilenet_web/static/description/icon.png"/>
        </xpath>
        <xpath expr="//snippets[@id='snippet_structure']" position="inside">''')
    for kind, spec in KINDS.items():
        out.append('            <t t-snippet="mirabilenet_web.%s" string="%s" group="mirabilenet">'
                   '\n                <keywords>mirabilenet, %s</keywords>\n            </t>' % (
                       spec[0], x(spec[1]), x(spec[1].lower())))
    out.append("        </xpath>\n    </template>\n</odoo>\n")
    return "\n".join(out)


def filters_xml():
    out = ['<?xml version="1.0" encoding="utf-8"?>', "<odoo>",
           "    <!-- Fuentes de los bloques dinámicos: leen con privilegios solo lo publicado. -->"]
    for kind, spec in KINDS.items():
        model = spec[2]
        model_ref = ("product.model_product_template" if model == "product.template"
                     else "model_" + model.replace(".", "_"))
        out.append('''    <record id="mn_action_%(kind)s" model="ir.actions.server">
        <field name="name">MIRABILENET: %(name)s (sitio web)</field>
        <field name="model_id" ref="%(model_ref)s"/>
        <field name="state">code</field>
        <field name="code">response = model.env['website.snippet.filter']._mirabilenet_records('%(kind)s')</field>
    </record>
    <record id="mn_filter_%(kind)s" model="website.snippet.filter">
        <field name="name">MIRABILENET: %(name)s</field>
        <field name="action_server_id" ref="mn_action_%(kind)s"/>
        <field name="field_names">%(fields)s</field>
        <field name="limit">16</field>
    </record>''' % dict(kind=kind, name=x(spec[1]), model_ref=model_ref, fields=spec[4]))
    out.append("</odoo>\n")
    return "\n".join(out)


def replace_pages(path):
    text = open(path, encoding="utf-8").read()
    for view_id in PAGES:
        pattern = re.compile(r'    <template id="%s".*?\n    </template>' % view_id, re.S)
        assert len(pattern.findall(text)) == 1, view_id
        text = pattern.sub(lambda _m: page(view_id), text, count=1)
    open(path, "w", encoding="utf-8", newline="\n").write(text)


if __name__ == "__main__":
    os.makedirs(os.path.join(MOD, "views", "snippets"), exist_ok=True)
    open(os.path.join(MOD, "views", "snippets", "mirabilenet_snippets.xml"), "w",
         encoding="utf-8", newline="\n").write(snippets_xml())
    open(os.path.join(MOD, "data", "website_snippet_filter_data.xml"), "w",
         encoding="utf-8", newline="\n").write(filters_xml())
    replace_pages(os.path.join(MOD, "views", "templates.xml"))
    print("generado:", ", ".join(KINDS), "|", ", ".join(PAGES))
