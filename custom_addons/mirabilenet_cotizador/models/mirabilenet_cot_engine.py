"""Puente entre Odoo y el motor puro del cotizador (cotizador/): le da el catálogo y la
configuración, y convierte su resultado en una cotización (sale.order)."""
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..cotizador import desde_texto, kits as kits_motor, precios, selector
from ..cotizador.quote import Cotizacion, GRUPOS
from .mirabilenet_cot_config import DEFAULTS, PARAM, config_from_env

GROUP_LABELS = {"equipos": "Equipos", "materiales": "Materiales", "mano_obra": "Mano de obra",
                "viaticos": "Viáticos"}
#: Producto genérico de cada grupo, para las líneas que no son un producto del catálogo.
GENERIC_PRODUCTS = {"materiales": "mirabilenet_cotizador.product_cot_material",
                    "mano_obra": "mirabilenet_cotizador.product_cot_labor",
                    "viaticos": "mirabilenet_cotizador.product_cot_travel",
                    "equipos": "mirabilenet_cotizador.product_cot_material"}
ORIGINS = [("oficina", "Oficina"), ("trabajador", "Trabajador por WhatsApp"),
           ("bot", "Bot de atención")]


class _Producto:
    """Un producto del catálogo, como lo espera el motor."""

    def __init__(self, record):
        self.record = record
        self.sku = record.mirabilenet_cot_sku or record.default_code or str(record.id)
        self.nombre = record.name or ""
        self.marca = record.mirabilenet_cot_brand or ""
        self.costo = precios.D(record.standard_price)
        self.categoria = record.mirabilenet_cot_category or ""
        self.subcategoria = record.mirabilenet_cot_subcategory or None
        self.descripcion = record.description_sale or ""
        self.precio_en = record.mirabilenet_cot_cost_at
        self.stock_total = record.mirabilenet_cot_stock_total or 0

    def stock_en(self, ciudad):
        return self.record._mirabilenet_cot_stock_in(ciudad)


class _Catalogo:
    def __init__(self, env):
        self.env = env
        self._cache = {}

    def productos(self, categorias):
        key = tuple(sorted(c.upper() for c in categorias))
        if key not in self._cache:
            Product = self.env["product.template"].sudo()
            domain = ["|"] * (len(key) - 1) + [("mirabilenet_cot_category", "=ilike", c)
                                               for c in key]
            self._cache[key] = [_Producto(p) for p in Product.search(
                domain + [("sale_ok", "=", True)])]
        return self._cache[key]

    def por_sku(self, sku):
        record = self.env["product.template"].sudo().search(
            [("mirabilenet_cot_sku", "=", sku)], limit=1)
        return _Producto(record) if record else None

    def tipo_cambio(self):
        Engine = self.env["mirabilenet.cot.engine"]
        return precios.TipoCambio(Engine._param_decimal("tipo_cambio_manual"),
                                  fields.Date.context_today(Engine), "manual")


class MirabilenetCotEngine(models.AbstractModel):
    _name = "mirabilenet.cot.engine"
    _description = "Cotizador: motor"

    # ------------------------------------------------------------------
    @api.model
    def _param(self, key):
        return self.env["ir.config_parameter"].sudo().get_param(PARAM + key, DEFAULTS[key])

    @api.model
    def _param_decimal(self, key):
        return precios.D(self._param(key))

    @api.model
    def _taxes_enabled(self):
        """Interruptor general de IVA + IT (Ajustes del cotizador)."""
        return self._param("impuestos_activos") in ("1", "True", "true")

    @api.model
    def _config(self):
        return config_from_env(self.env)

    @api.model
    def _kits(self):
        return {k.code: k.definition for k in self.env["mirabilenet.cot.kit"].sudo().search([])}

    @api.model
    def _cities(self):
        return self.env["mirabilenet.cot.city"].sudo().search([]).mapped("name")

    # ------------------------------------------------------------------
    # Crear cotizaciones
    # ------------------------------------------------------------------
    @api.model
    def create_from_kit(self, kit, city, partner, invoice=None, meters=None, km=0, title=None,
                        origin="oficina", notes=None, requester=None):
        """kit: un mirabilenet.cot.kit o la definición (dict) de uno."""
        definition = kit.definition if isinstance(kit, models.BaseModel) else kit
        definition = dict(definition, nombre=definition.get("nombre") or (
            kit.name if isinstance(kit, models.BaseModel) else ""))
        cfg = self._config()
        try:
            quote = kits_motor.armar_kit(_Catalogo(self.env), cfg, definition, city,
                                         facturar=invoice, metros=meters, km=km or 0,
                                         titulo=title)
        except ValueError as exc:
            raise UserError(str(exc)) from exc
        if notes:
            quote.notas.insert(0, notes)
        return self._save(quote, cfg, partner, origin,
                          kit if isinstance(kit, models.BaseModel) else None, requester)

    @api.model
    def create_from_text(self, text, city, partner, invoice=None, origin="oficina",
                         requirements=None, requester=None):
        """Del pedido escrito, o de requisitos ya armados (por la IA de n8n), a una cotización.
        Las reglas mandan sobre lo que dice el texto; precios y SKU los pone el motor."""
        try:
            req = requirements or desde_texto.requisitos_desde_texto(text or "")
            definition = desde_texto.kit_desde_requisitos(req, self._kits())
        except desde_texto.PedidoError as exc:
            raise UserError(str(exc)) from exc
        notes = _("Pedido: «%s»", (text or "").strip()[:400]) if text else None
        order = self.create_from_kit(definition, city, partner, invoice=invoice,
                                     meters=req.get("metros"), title=definition["nombre"],
                                     origin=origin, notes=notes, requester=requester)
        if req.get("dudas"):
            order.mirabilenet_cot_alerts = "\n".join(
                ["Revisar: %s" % d for d in req["dudas"]]
                + ([order.mirabilenet_cot_alerts] if order.mirabilenet_cot_alerts else []))
        return order

    @api.model
    def create_from_products(self, items, city, partner, invoice=None, origin="oficina",
                             title=None, requester=None):
        """Cotización de productos sueltos: items = [(product.template, cantidad)]."""
        cfg = self._config()
        quote = Cotizacion(cfg=cfg, ciudad=city,
                           facturar=cfg.facturar_por_defecto if invoice is None else invoice,
                           tipo_cambio=_Catalogo(self.env).tipo_cambio(),
                           titulo=title or _("Cotización de equipos"))
        now = datetime.utcnow()
        for product, qty in items:
            producto = _Producto(product.sudo())
            stock = producto.stock_en(city)
            candidate = selector.Candidato(producto, selector.specs_de(producto), stock,
                                           motivo="pedido directo")
            line = kits_motor.linea_producto(cfg, candidate, qty, now)
            if stock is not None and stock < qty:
                line.alertas.append(_("Sin stock suficiente en %(c)s (%(s)s de %(q)s)",
                                      c=city, s=stock, q=qty))
            quote.lineas.append(line)
        return self._save(quote, cfg, partner, origin, None, requester)

    # ------------------------------------------------------------------
    @api.model
    def _save(self, quote, cfg, partner, origin, kit, requester):
        if not quote.lineas:
            raise UserError(_("El motor no encontró productos para cotizar: %s",
                              "; ".join(quote.todas_alertas()) or "-"))
        Product = self.env["product.product"].sudo()
        lines = []
        for group in GRUPOS:
            group_lines = [l for l in quote.lineas if l.grupo == group]
            if not group_lines:
                continue
            lines.append((0, 0, {"display_type": "line_section",
                                 "name": GROUP_LABELS[group]}))
            for l in group_lines:
                product = Product.browse()
                if l.sku:
                    template = self.env["product.template"].sudo().search(
                        [("mirabilenet_cot_sku", "=", l.sku)], limit=1)
                    product = template.product_variant_id
                if not product:
                    product = self.env.ref(GENERIC_PRODUCTS[group])
                lines.append((0, 0, {
                    "product_id": product.id, "name": l.descripcion,
                    "product_uom_qty": float(l.cantidad), "price_unit": float(l.precio_unit),
                    "tax_ids": [(6, 0, [])], "mirabilenet_cot_frozen": True,
                    "mirabilenet_cot_group": group,
                    "mirabilenet_cot_unit": l.unidad,
                    "mirabilenet_cot_cost": float(l.costo_unit) if l.costo_unit is not None else 0,
                    "mirabilenet_cot_markup": float(l.recargo * 100) if l.recargo is not None
                    else 0,
                    "mirabilenet_cot_stock": l.stock_ciudad if l.stock_ciudad is not None else -1,
                    "mirabilenet_cot_reason": l.motivo or False,
                    "mirabilenet_cot_alerts": "\n".join(l.alertas) or False,
                }))
        storage = quote.almacenamiento.texto() if quote.almacenamiento else False
        today = fields.Date.context_today(self)
        city = self.env["mirabilenet.cot.city"].sudo().search([("name", "=", quote.ciudad)],
                                                               limit=1)
        order = self.env["sale.order"].sudo().create({
            "partner_id": partner.id,
            "mirabilenet_cot_is_quote": True,
            "mirabilenet_cot_title": quote.titulo or False,
            "mirabilenet_cot_origin": origin,
            "mirabilenet_cot_city_id": city.id,
            "mirabilenet_cot_invoice": bool(quote.facturar) and self._taxes_enabled(),
            "mirabilenet_cot_rate": float(quote.tipo_cambio.valor),
            "mirabilenet_cot_tax_mode": cfg.modo_impuestos,
            "mirabilenet_cot_iva_rate": float(cfg.iva),
            "mirabilenet_cot_it_rate": float(cfg.it),
            "mirabilenet_cot_kit_id": kit.id if kit else False,
            "mirabilenet_cot_alerts": "\n".join(quote.alertas) or False,
            "mirabilenet_cot_notes": "\n\n".join(quote.notas) or False,
            "mirabilenet_cot_storage": storage,
            "mirabilenet_cot_requester_id": (requester or self.env.user).id,
            "validity_date": today + timedelta(days=cfg.vigencia_dias),
            "order_line": lines,
        })
        order.message_post(body=_("Cotización armada por el motor (%s).",
                                  dict(ORIGINS).get(origin, origin)))
        return order
