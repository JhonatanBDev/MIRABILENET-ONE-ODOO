import hashlib
import json
import uuid

from odoo import api, fields, models

from ..siat import constants
from ..siat.payment_methods import components_key, decompose

CATALOG_TYPES = [
    ("actividades", "Actividades económicas"),
    ("actividades_documento_sector", "Actividades por documento sector"),
    ("leyendas", "Leyendas de factura"),
    ("mensajes_servicios", "Mensajes de servicios"),
    ("productos_servicios", "Productos y servicios"),
    ("eventos_significativos", "Eventos significativos"),
    ("motivo_anulacion", "Motivos de anulación"),
    ("pais_origen", "Países de origen"),
    ("tipo_documento_identidad", "Tipos de documento de identidad"),
    ("tipo_documento_sector", "Tipos de documento sector"),
    ("tipo_emision", "Tipos de emisión"),
    ("tipo_metodo_pago", "Métodos de pago"),
    ("tipo_moneda", "Monedas"),
    ("tipo_punto_venta", "Tipos de punto de venta"),
    ("tipos_factura", "Tipos de factura"),
    ("unidad_medida", "Unidades de medida"),
]


def _normalize(catalog_type, row):
    """Lleva cada fila del SIN a (code, name, activity_code, extra)."""
    if catalog_type == "actividades":
        return (row.get("codigoCaeb"), row.get("descripcion"), "", row.get("tipoActividad"))
    if catalog_type == "productos_servicios":
        return (row.get("codigoProducto"), row.get("descripcionProducto"),
                row.get("codigoActividad"), "")
    if catalog_type == "leyendas":
        text = row.get("descripcionLeyenda") or ""
        return (hashlib.sha256(text.encode("utf-8")).hexdigest()[:10], text,
                row.get("codigoActividad"), "")
    if catalog_type == "actividades_documento_sector":
        return (row.get("codigoDocumentoSector"), row.get("tipoDocumentoSector"),
                row.get("codigoActividad"), "")
    return (row.get("codigoClasificador"), row.get("descripcion"), "", "")


class MiraSiatCatalog(models.Model):
    """Catálogo oficial sincronizado, con fecha y huella de versión."""
    _name = "mira.siat.catalog"
    _description = "Mira_Sale SIAT: catálogo sincronizado"
    _order = "company_id, catalog_type"
    _rec_name = "catalog_type"

    company_id = fields.Many2one("res.company", string="Empresa", required=True, index=True)
    catalog_type = fields.Selection(CATALOG_TYPES, string="Catálogo", required=True)
    version_hash = fields.Char(string="Huella de versión (SHA-256)", readonly=True)
    synced_at = fields.Datetime(string="Sincronizado el", readonly=True)
    item_ids = fields.One2many("mira.siat.catalog.item", "catalog_id", string="Elementos")
    item_count = fields.Integer(compute="_compute_item_count", string="Elementos vigentes")

    _company_type_uniq = models.Constraint(
        "unique(company_id, catalog_type)", "El catálogo ya existe para esta empresa.")

    @api.depends("item_ids")
    def _compute_item_count(self):
        for catalog in self:
            catalog.item_count = len(catalog.item_ids)

    def _update_payment_components(self):
        """Deduce qué medios simples componen cada método de pago."""
        self.ensure_one()
        items = self.env["mira.siat.catalog.item"].sudo().search(
            [("catalog_id", "=", self.id)])
        parsed = decompose({item.id: item.name for item in items})
        for item in items:
            components = parsed.get(item.id)
            upper = (item.name or "").upper()
            vals = {
                "components": components_key(components),
                # Si el nombre no se pudo interpretar, se cae al texto literal.
                "includes_card": any("TARJETA" in c for c in components) if components
                else "TARJETA" in upper,
                "includes_gift_card": any(c.startswith("GIFT") for c in components)
                if components else "GIFT" in upper,
            }
            if any(item[f] != v for f, v in vals.items()):
                item.write(vals)

    @api.model
    def _sync(self, pos, catalog_types=None):
        """Sincroniza los catálogos de la empresa del punto de venta."""
        service = self.env["mira.siat.service"]
        company = pos.company_id
        company._mira_siat_check_active()
        correlation = str(uuid.uuid4())
        gateway = company._mira_siat_gateway(correlation)
        ctx = pos._siat_context()
        cuis = pos._get_cuis()._code()
        Item = self.env["mira.siat.catalog.item"].sudo().with_context(active_test=False)
        summary = {}
        for catalog_type in catalog_types or list(constants.CATALOG_OPERATIONS):
            rows = gateway.sync_catalog(ctx, cuis, catalog_type)
            entries = sorted({_normalize(catalog_type, r) for r in rows if r},
                             key=lambda e: tuple(x or "" for x in e))
            entries = [e for e in entries if e[0]]
            version = hashlib.sha256(
                json.dumps(entries, ensure_ascii=False).encode("utf-8")).hexdigest()
            catalog = self.sudo().search(
                [("company_id", "=", company.id), ("catalog_type", "=", catalog_type)],
                limit=1)
            if not catalog:
                catalog = self.sudo().create(
                    {"company_id": company.id, "catalog_type": catalog_type})
            existing = {
                (i.code, i.activity_code or ""): i
                for i in Item.search([("catalog_id", "=", catalog.id)])
            }
            seen = set()
            to_create = []
            for code, name, activity, extra in entries:
                key = (str(code), activity or "")
                seen.add(key)
                vals = {"name": name or str(code), "extra": extra or False, "active": True}
                if key in existing:
                    item = existing[key]
                    if (item.name, item.extra or False, item.active) != (
                            vals["name"], vals["extra"], True):
                        item.write(vals)
                else:
                    to_create.append(dict(
                        vals, catalog_id=catalog.id, code=str(code),
                        activity_code=activity or False))
            Item.create(to_create)
            # Lo que el SIN ya no publica se archiva: los documentos emitidos
            # conservan su referencia.
            for key, item in existing.items():
                if key not in seen and item.active:
                    item.active = False
            if catalog_type == "tipo_metodo_pago":
                catalog._update_payment_components()
            catalog.write({"version_hash": version, "synced_at": fields.Datetime.now()})
            summary[catalog_type] = version
        service._audit("catalogs.sync", pos, after=summary, correlation_id=correlation)
        return True
