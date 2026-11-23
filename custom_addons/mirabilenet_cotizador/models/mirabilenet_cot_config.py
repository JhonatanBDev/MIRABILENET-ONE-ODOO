"""Configuración del cotizador, editable en Odoo: recargos, materiales, mano de obra, ciudades y
kits. Los recargos reales (márgenes) se cargan en cada base; el repositorio solo trae ejemplos."""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..cotizador import precios

PARAM = "mirabilenet_cotizador."
#: Parámetros generales y su valor por defecto.
DEFAULTS = {
    "recargo_defecto": "0.30",
    "recargo_maximo": "0.75",
    "recargo_maximo_bajo": "1.50",
    "iva": "0.13",
    "it": "0.03",
    "modo_impuestos": "agregar",
    "facturar_por_defecto": "1",
    "vigencia_dias": "5",
    "redondeo_multiplo": "5",
    "redondeo_umbral_bajo": "50",
    "redondeo_multiplo_bajo": "0.5",
    "redondeo_total": "0",
    "precio_max_horas": "24",
    "marcas_preferidas": "DAHUA, HIKVISION, EZVIZ, UNIVIEW, MIKROTIK, UBIQUITI, TP-LINK",
    "bonus_marca_preferida": "0.15",
    "tipo_cambio_manual": "6.96",
    "viaticos_por_km": "3",
}


class MirabilenetCotMarkup(models.Model):
    """Un recargo sobre el costo: por categoría de DigiCorp, o por costo del ítem (los baratos)."""
    _name = "mirabilenet.cot.markup"
    _description = "Cotizador: recargo"
    _order = "kind, below, category"

    kind = fields.Selection([("categoria", "Por categoría"), ("costo", "Por costo del ítem")],
                            string="Tipo", required=True, default="categoria")
    category = fields.Char(string="Categoría DigiCorp",
                           help="Nombre de la categoría (nivel 2) o subcategoría, por ejemplo "
                                "CAMARAS IP. Sin distinguir mayúsculas.")
    below = fields.Float(string="Costo menor a (Bs)",
                         help="Para el tipo «por costo»: ítems más baratos que esto.")
    markup = fields.Float(string="Recargo (%)", required=True,
                          help="Sobre el costo: 60 quiere decir +60 %.")
    active = fields.Boolean(default=True)

    @api.constrains("kind", "category", "below", "markup")
    def _check_markup(self):
        Engine = self.env["mirabilenet.cot.engine"]
        for rule in self:
            if rule.kind == "categoria" and not (rule.category or "").strip():
                raise ValidationError(_("Indique la categoría."))
            if rule.kind == "costo" and rule.below <= 0:
                raise ValidationError(_("Indique el costo tope del escalón."))
            top = Engine._param_decimal("recargo_maximo_bajo" if rule.kind == "costo"
                                        else "recargo_maximo") * 100
            if rule.markup < 0 or rule.markup > top:
                raise ValidationError(_("El recargo debe estar entre 0 %% y %s %%.", float(top)))


class MirabilenetCotMaterial(models.Model):
    _name = "mirabilenet.cot.material"
    _description = "Cotizador: material"
    _order = "code"

    code = fields.Char(string="Clave", required=True)
    name = fields.Char(string="Descripción", required=True)
    category = fields.Char(string="Categoría DigiCorp donde se busca")
    words = fields.Char(string="Palabras que deben estar en el nombre",
                        help="Separadas por coma.")
    exclude = fields.Char(string="Descartar si el nombre tiene (regex)")
    sku = fields.Char(string="SKU fijo", help="Si se indica, se usa siempre ese producto.")
    unit = fields.Selection([("u", "Unidad"), ("m", "Metro")], string="Unidad", default="u",
                            required=True)
    purchase_unit = fields.Float(string="Unidades por ítem", default=1,
                                 help="Metros o unidades que trae un ítem si el nombre no lo dice.")
    price_ref = fields.Float(string="Costo de referencia (Bs)", required=True,
                             help="Se usa si no hay producto con stock: queda como alerta.")
    optional = fields.Boolean(string="Opcional",
                              help="Si no hay stock suficiente en la ciudad, se quita del kit.")

    _code_uniq = models.Constraint("unique(code)", "Esa clave ya existe.")


class MirabilenetCotTariff(models.Model):
    _name = "mirabilenet.cot.tariff"
    _description = "Cotizador: tarifa de mano de obra"
    _order = "code"

    code = fields.Char(string="Clave", required=True)
    name = fields.Char(string="Descripción", required=True)
    price = fields.Float(string="Precio (Bs)", required=True)
    unit = fields.Char(string="Unidad", default="u", required=True)

    _code_uniq = models.Constraint("unique(code)", "Esa clave ya existe.")


class MirabilenetCotCity(models.Model):
    _name = "mirabilenet.cot.city"
    _description = "Cotizador: ciudad"
    _order = "sequence, name"

    name = fields.Char(string="Ciudad", required=True,
                       help="Igual que la ciudad de los almacenes de DigiCorp.")
    sequence = fields.Integer(default=10)
    viatico = fields.Float(string="Viáticos (Bs)", help="Movilidad y viáticos hasta esa ciudad.")
    is_base = fields.Boolean(string="Ciudad base")
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint("unique(name)", "Esa ciudad ya existe.")


class MirabilenetCotKit(models.Model):
    """Kit plantilla: cámaras por ubicación, grabación, NVR, cable, materiales y mano de obra.
    La definición es la misma del cotizador original (referencia/config/kits.yaml)."""
    _name = "mirabilenet.cot.kit"
    _description = "Cotizador: kit"
    _order = "sequence, name"

    code = fields.Char(string="Clave", required=True)
    name = fields.Char(string="Nombre", required=True)
    sequence = fields.Integer(default=10)
    definition = fields.Json(string="Definición", required=True)
    cameras = fields.Integer(string="Cámaras", compute="_compute_summary")
    technology = fields.Char(string="Tecnología", compute="_compute_summary")
    range_ = fields.Char(string="Gama", compute="_compute_summary")
    days = fields.Integer(string="Días de grabación", compute="_compute_summary")
    offer_bot = fields.Boolean(string="Ofrecer en el bot", default=True)
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("unique(code)", "Esa clave ya existe.")

    @api.depends("definition")
    def _compute_summary(self):
        for kit in self:
            d = kit.definition or {}
            kit.cameras = sum(int(c.get("cantidad") or 0) for c in d.get("camaras") or [])
            kit.technology = "Analógica" if d.get("tecnologia") == "analogica" else "IP"
            kit.range_ = "Económica" if d.get("gama") == "economica" else "Estándar"
            kit.days = int(d.get("dias_grabacion") or 15)

    @api.constrains("definition")
    def _check_definition(self):
        for kit in self:
            d = kit.definition
            if not isinstance(d, dict) or not d.get("camaras"):
                raise ValidationError(_("La definición del kit necesita al menos un grupo de "
                                        "cámaras."))


def config_from_env(env):
    """Arma la configuración del motor desde las reglas y parámetros de Odoo."""
    Engine = env["mirabilenet.cot.engine"]
    dec = Engine._param_decimal
    markups = env["mirabilenet.cot.markup"].sudo().search([])
    materials = {}
    for m in env["mirabilenet.cot.material"].sudo().search([]):
        buscar = precios.Buscar(
            m.category, [w.strip().upper() for w in (m.words or "").split(",") if w.strip()],
            m.exclude or None) if m.category else None
        materials[m.code] = precios.Material(
            m.name, precios.D(m.price_ref), buscar=buscar, sku=m.sku or None, unidad=m.unit,
            unidad_compra=precios.D(m.purchase_unit or 1), opcional=m.optional)
    tariffs = {t.code: precios.Tarifa(precios.D(t.price), t.unit, t.name)
               for t in env["mirabilenet.cot.tariff"].sudo().search([])}
    cities = env["mirabilenet.cot.city"].sudo().search([])
    base = cities.filtered("is_base")[:1] or cities[:1]
    return precios.Config(
        recargo_defecto=dec("recargo_defecto"),
        recargo_maximo=dec("recargo_maximo"),
        recargo_maximo_bajo=dec("recargo_maximo_bajo"),
        por_categoria={r.category: precios.D(r.markup) / 100
                       for r in markups if r.kind == "categoria"},
        por_costo=[(precios.D(r.below), precios.D(r.markup) / 100)
                   for r in markups if r.kind == "costo"],
        iva=dec("iva"), it=dec("it"),
        modo_impuestos=Engine._param("modo_impuestos"),
        facturar_por_defecto=Engine._param("facturar_por_defecto") in ("1", "True", "true"),
        vigencia_dias=int(dec("vigencia_dias")),
        redondeo_multiplo=dec("redondeo_multiplo"),
        redondeo_umbral_bajo=dec("redondeo_umbral_bajo"),
        redondeo_multiplo_bajo=dec("redondeo_multiplo_bajo"),
        redondeo_total=dec("redondeo_total"),
        precio_max_horas=float(dec("precio_max_horas")),
        marcas_preferidas=[m.strip().upper() for m in Engine._param("marcas_preferidas").split(",")
                           if m.strip()],
        bonus_marca_preferida=float(dec("bonus_marca_preferida")),
        tipo_cambio_manual=dec("tipo_cambio_manual"),
        materiales=materials, mano_obra=tariffs,
        viaticos=precios.Viaticos(
            ciudad_base=base.name or "La Paz",
            por_ciudad={c.name: precios.D(c.viatico) for c in cities},
            por_km=dec("viaticos_por_km")),
    )
