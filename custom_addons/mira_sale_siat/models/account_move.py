import random
import re
from decimal import Decimal

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..siat import constants
from ..siat.amounts import dec, fmt, money
from .mira_siat_invoice import ACCEPTED_BY_SIN, LIVE_STATES, STATES

FISCAL_MOVE_TYPES = ("out_invoice", "out_refund")
# Medios que implican un cobro ya realizado: no se declaran en una venta a
# crédito que todavía no tiene pagos.
_IMMEDIATE = ("EFECTIVO", "TARJETA", "CHEQUE", "GIFT")


def mask_card(number):
    """Primeros 4 y últimos 4 dígitos; el centro se reemplaza por ceros. El
    número completo nunca se guarda ni se transmite. Acepta un número ya
    enmascarado con asteriscos o equis."""
    positions = re.sub(r"[^0-9*xX]", "", number or "")
    if not positions:
        return False
    if len(positions) < 8:
        raise UserError(_("El número de tarjeta debe tener al menos 8 posiciones."))
    clean = re.sub(r"[*xX]", "0", positions)
    return clean[:4] + "0" * 8 + clean[-4:]


class AccountMove(models.Model):
    _inherit = "account.move"

    mira_siat_enabled = fields.Boolean(related="company_id.mira_siat_enabled")
    mira_siat_pos_id = fields.Many2one(
        "mira.siat.pos", string="Punto de venta SIAT", copy=False,
        domain="[('company_id', '=', company_id), ('code', '>=', 0)]",
        compute="_compute_mira_siat_pos_id", store=True, readonly=False)
    mira_siat_sector = fields.Selection(
        [("1", "Factura de Compra y Venta"), ("22", "Factura de Telecomunicaciones")],
        string="Documento sector", compute="_compute_mira_siat_sector", store=True,
        readonly=False)
    mira_siat_joint_nit = fields.Char(
        string="NIT conjunto", copy=False,
        help="Solo para Factura de Telecomunicaciones emitida en forma conjunta.")

    # Método de pago
    mira_siat_payment_method_id = fields.Many2one(
        "mira.siat.catalog.item", string="Método de pago SIAT", copy=False,
        domain="[('catalog_type', '=', 'tipo_metodo_pago'), ('company_id', '=', company_id)]")
    mira_siat_payment_method_manual = fields.Boolean(
        string="Método elegido a mano", copy=False,
        help="Si está marcado, el sistema no reemplaza el método por el deducido.")
    mira_siat_suggested_method_id = fields.Many2one(
        "mira.siat.catalog.item", string="Método sugerido",
        compute="_compute_mira_siat_suggested_method_id")
    mira_siat_method_includes_card = fields.Boolean(
        related="mira_siat_payment_method_id.includes_card")
    mira_siat_method_includes_gift = fields.Boolean(
        related="mira_siat_payment_method_id.includes_gift_card")
    mira_siat_card_number = fields.Char(
        string="Tarjeta (enmascarada)", copy=False,
        help="Se guarda solo enmascarada: 4 primeros y 4 últimos dígitos.")
    mira_siat_gift_card_amount = fields.Monetary(string="Monto gift card", copy=False)

    # Cliente e importes
    mira_siat_force_invalid_nit = fields.Boolean(
        string="Emitir aunque el NIT no esté activo", copy=False,
        help="Envía el código de excepción al SIN para esta factura.")
    mira_siat_global_discount = fields.Monetary(
        string="Descuento global", copy=False,
        help="Descuento sobre el total. «Aplicar» lo convierte en una línea de descuento.")

    # Contingencia en papel y fecha anterior
    mira_siat_manual = fields.Boolean(
        string="Factura manual de contingencia", copy=False,
        help="Transcripción de una factura emitida en papel con un talonario CAFC.")
    mira_siat_manual_number = fields.Integer(string="N.º de la factura en papel", copy=False)
    mira_siat_manual_date = fields.Datetime(string="Fecha y hora del papel", copy=False)
    mira_siat_backdate = fields.Datetime(
        string="Emitir con fecha anterior", copy=False,
        help="Requiere una autorización vigente y un evento de regularización abierto.")
    mira_siat_can_backdate = fields.Boolean(compute="_compute_mira_siat_can_backdate")

    # Documento fiscal
    mira_siat_invoice_ids = fields.One2many(
        "mira.siat.invoice", "move_id", string="Documentos fiscales")
    mira_siat_invoice_id = fields.Many2one(
        "mira.siat.invoice", string="Documento fiscal",
        compute="_compute_mira_siat_invoice_id")
    mira_siat_state = fields.Selection(
        STATES, string="Estado fiscal", compute="_compute_mira_siat_invoice_id")
    mira_siat_cuf = fields.Char(string="CUF", compute="_compute_mira_siat_invoice_id")

    # ---- cálculos ---------------------------------------------------------
    @api.depends("company_id", "move_type")
    def _compute_mira_siat_pos_id(self):
        for move in self:
            if move.mira_siat_pos_id and move.mira_siat_pos_id.company_id == move.company_id:
                continue
            if move.move_type not in FISCAL_MOVE_TYPES or not move.company_id.mira_siat_enabled:
                move.mira_siat_pos_id = False
                continue
            move.mira_siat_pos_id = move.company_id._mira_siat_default_pos()

    @api.depends("journal_id", "company_id")
    def _compute_mira_siat_sector(self):
        for move in self:
            move.mira_siat_sector = (
                move.journal_id.mira_siat_sector or move.company_id.mira_siat_default_sector)

    @api.depends("mira_siat_invoice_ids.state", "mira_siat_invoice_ids.cuf")
    def _compute_mira_siat_invoice_id(self):
        for move in self:
            docs = move.mira_siat_invoice_ids.sorted("id", reverse=True)
            current = docs.filtered(lambda d: d.state != "rejected")[:1] or docs[:1]
            move.mira_siat_invoice_id = current
            move.mira_siat_state = current.state
            move.mira_siat_cuf = current.cuf

    @api.depends("reconciled_payment_ids", "matched_payment_ids", "invoice_date_due",
                 "invoice_date", "company_id")
    def _compute_mira_siat_suggested_method_id(self):
        for move in self:
            move.mira_siat_suggested_method_id = (
                move._mira_siat_derived_method() if move.move_type == "out_invoice" else False)

    @api.depends_context("uid")
    def _compute_mira_siat_can_backdate(self):
        allowed = self.env.user.has_group("mira_sale_siat.group_mira_siat_backdate")
        Auth = self.env["mira.siat.retro.authorization"]
        for move in self:
            move.mira_siat_can_backdate = allowed and bool(
                Auth._current(move.company_id))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("mira_siat_card_number"):
                vals["mira_siat_card_number"] = mask_card(vals["mira_siat_card_number"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("mira_siat_card_number"):
            vals["mira_siat_card_number"] = mask_card(vals["mira_siat_card_number"])
        if "mira_siat_payment_method_id" in vals \
                and "mira_siat_payment_method_manual" not in vals \
                and not self.env.context.get("mira_siat_auto_method"):
            vals["mira_siat_payment_method_manual"] = bool(vals["mira_siat_payment_method_id"])
        return super().write(vals)

    # ---- protección del documento comercial ------------------------------
    def _mira_siat_check_no_live_document(self):
        for move in self:
            live = move.mira_siat_invoice_ids.filtered(lambda d: d.state in LIVE_STATES)
            if live:
                raise UserError(_(
                    "La factura %(move)s tiene un documento fiscal vigente (%(doc)s). "
                    "Anúlelo ante el SIN antes de modificar o cancelar la venta.",
                    move=move.display_name, doc=live[0].name))

    def button_draft(self):
        self._mira_siat_check_no_live_document()
        return super().button_draft()

    def button_cancel(self):
        self._mira_siat_check_no_live_document()
        return super().button_cancel()

    # ---- método de pago ---------------------------------------------------
    def _mira_siat_payments(self):
        self.ensure_one()
        return self.reconciled_payment_ids | self.matched_payment_ids.filtered(
            lambda p: p.state not in ("draft", "canceled", "rejected"))

    def _mira_siat_on_credit(self):
        """La factura nace para cobrarse después (plazo posterior a la fecha)."""
        self.ensure_one()
        return bool(self.invoice_date and self.invoice_date_due
                    and self.invoice_date_due > self.invoice_date)

    def _mira_siat_derived_method(self):
        """Método que corresponde según los cobros y el plazo; vacío si no se
        puede deducir con seguridad."""
        self.ensure_one()
        Item = self.env["mira.siat.catalog.item"].sudo()
        company = self.company_id
        payments = self._mira_siat_payments()
        if payments:
            components = set()
            for journal in payments.mapped("journal_id"):
                method = journal.mira_siat_payment_method_id
                if not method or not method.components:
                    return Item
                components.update(method.components.split("|"))
            return Item.search([
                ("company_id", "=", company.id), ("catalog_type", "=", "tipo_metodo_pago"),
                ("components", "=", "|".join(sorted(components))),
            ], limit=1)
        if self._mira_siat_on_credit():
            return company.mira_siat_credit_payment_method_id
        return Item

    def _mira_siat_resolve_payment_method(self):
        """Aplica el método deducido (salvo elección manual) y verifica que no
        se declare un cobro que no ocurrió."""
        self.ensure_one()
        company = self.company_id
        derived = self._mira_siat_derived_method()
        if derived and not self.mira_siat_payment_method_manual \
                and derived != self.mira_siat_payment_method_id:
            self.with_context(mira_siat_auto_method=True).write(
                {"mira_siat_payment_method_id": derived.id})
        method = self.mira_siat_payment_method_id or company.mira_siat_default_payment_method_id
        if not method:
            raise UserError(_("Seleccione el método de pago SIAT."))
        if self._mira_siat_on_credit() and not self._mira_siat_payments():
            text = (method.components or method.name or "").upper()
            if any(word in text for word in _IMMEDIATE):
                raise UserError(_(
                    "La factura es a crédito y todavía no tiene cobros: no se puede "
                    "declarar «%(method)s». Use el método de pago para ventas a crédito "
                    "(%(credit)s) o registre el cobro antes de emitir.",
                    method=method.name,
                    credit=company.mira_siat_credit_payment_method_id.name
                    or _("configúrelo en la empresa")))
        return method

    # ---- descuento global -------------------------------------------------
    def _mira_siat_discount_product(self):
        product = self.env.ref("mira_sale_siat.product_global_discount",
                               raise_if_not_found=False)
        if not product:
            product = self.env["product.product"].search(
                [("mira_siat_is_discount", "=", True)], limit=1)
        if not product:
            raise UserError(_("No existe un producto marcado como descuento."))
        return product

    def action_mira_siat_apply_global_discount(self):
        """Convierte el descuento global en una única línea negativa."""
        for move in self:
            if move.state != "draft":
                raise UserError(_("El descuento global se aplica en borrador."))
            product = move._mira_siat_discount_product()
            lines = move.invoice_line_ids.filtered(lambda l: l.display_type == "product")
            previous = lines.filtered(lambda l: l.product_id.mira_siat_is_discount)
            base = (lines - previous)[:1]
            commands = [(2, line.id) for line in previous]
            if move.mira_siat_global_discount > 0:
                if not base:
                    raise UserError(_("Agregue al menos un producto antes del descuento."))
                commands.append((0, 0, {
                    "product_id": product.id,
                    "name": _("Descuento"),
                    "quantity": 1,
                    "price_unit": -move.mira_siat_global_discount,
                    "tax_ids": [(6, 0, base.tax_ids.ids)],
                }))
            move.write({"invoice_line_ids": commands})
        return True

    # ---- moneda -----------------------------------------------------------
    def _mira_siat_currency(self):
        """(código de moneda SIN, tipo de cambio a la moneda de la empresa).

        La contabilidad de la empresa debe llevarse en bolivianos: los
        importes fiscales se expresan en esa moneda."""
        self.ensure_one()
        company = self.company_id
        Item = self.env["mira.siat.catalog.item"].sudo()
        if self.currency_id == company.currency_id:
            item = Item.search([
                ("company_id", "=", company.id), ("catalog_type", "=", "tipo_moneda"),
                ("currency_id", "=", self.currency_id.id)], limit=1) \
                or company.mira_siat_currency_item_id
            if not item:
                raise UserError(_(
                    "Configure la moneda SIAT de la empresa (catálogo de monedas del SIN)."))
            return int(item.code), Decimal("1")
        item = Item.search([
            ("company_id", "=", company.id), ("catalog_type", "=", "tipo_moneda"),
            ("currency_id", "=", self.currency_id.id)], limit=1)
        if not item:
            raise UserError(_(
                "La moneda %s no está vinculada a ningún código del catálogo de monedas "
                "del SIN. Vincúlela en Configuración SIAT > Catálogos.", self.currency_id.name))
        date = self.invoice_date or fields.Date.context_today(self)
        rate = money(self.env["res.currency"]._get_conversion_rate(
            self.currency_id, company.currency_id, company, date))
        if rate <= 0:
            raise UserError(_("No hay tipo de cambio válido para %s.", self.currency_id.name))
        return int(item.code), rate

    # ---- líneas -----------------------------------------------------------
    def _mira_siat_lines(self, rate=Decimal("1")):
        """Ítems facturables: productos con precio positivo que no son
        descuentos. Importes con impuesto incluido, en moneda de la empresa."""
        self.ensure_one()
        company = self.company_id
        lines, missing = [], []
        for line in self.invoice_line_ids.filtered(lambda l: l.display_type == "product"):
            if line.product_id.mira_siat_is_discount or line.price_unit <= 0:
                continue
            mapping = line.product_id.product_tmpl_id._mira_siat_mapping(company) \
                if line.product_id else None
            if not mapping:
                missing.append(line.name or line.product_id.display_name or "?")
                continue
            activity, siat_product, unit = mapping
            quantity = money(line.quantity)
            if quantity != dec(line.quantity) or quantity <= 0:
                raise UserError(_(
                    "Línea «%s»: la cantidad debe ser positiva y con máximo 2 decimales.",
                    line.name))
            if line.discount >= 100:
                raise UserError(_(
                    "Línea «%s»: no se admite un descuento del 100 %%.", line.name))
            taxes = line.tax_ids.compute_all(
                line.price_unit, currency=self.currency_id, quantity=1.0,
                product=line.product_id, partner=self.partner_id)
            unit_price = money(dec(taxes["total_included"]) * rate)
            gross = money(quantity * unit_price)
            discount = money(gross * dec(line.discount) / 100)
            subtotal = gross - discount
            if unit_price <= 0 or subtotal <= 0:
                raise UserError(_("Línea «%s»: el importe debe ser mayor a cero.", line.name))
            lines.append({
                "activity_code": activity.code,
                "siat_product_code": siat_product.code,
                "product_code": (line.product_id.default_code or "P%s" % line.product_id.id)[:50],
                "description": (line.name or line.product_id.display_name)[:500],
                "quantity": quantity,
                "unit_code": unit.code,
                "unit_price": unit_price,
                "discount": discount,
                "subtotal": subtotal,
            })
        if missing:
            raise UserError(_(
                "Productos sin homologar (actividad, producto SIN y unidad): %s",
                ", ".join(missing)))
        if not lines:
            raise UserError(_("La factura no tiene líneas facturables."))
        return lines

    def _mira_siat_legend(self, activity_code):
        legends = self.env["mira.siat.catalog.item"].sudo().search([
            ("company_id", "=", self.company_id.id), ("catalog_type", "=", "leyendas"),
            ("activity_code", "=", activity_code)])
        if not legends:
            raise UserError(_(
                "No hay leyendas sincronizadas para la actividad %s. Sincronice los "
                "catálogos.", activity_code))
        return random.choice(legends).name[:200]

    def _mira_siat_check_sector(self, sector, lines):
        """El SIN publica qué documento sector admite cada actividad."""
        Item = self.env["mira.siat.catalog.item"].sudo()
        base = [("company_id", "=", self.company_id.id),
                ("catalog_type", "=", "actividades_documento_sector")]
        if not Item.search_count(base):
            return
        for activity in {line["activity_code"] for line in lines}:
            if not Item.search_count(
                    base + [("code", "=", str(sector)), ("activity_code", "=", activity)]):
                raise UserError(_(
                    "La actividad económica %(activity)s no está habilitada para el "
                    "documento sector %(sector)s según el catálogo del SIN.",
                    activity=activity, sector=sector))

    def _mira_siat_header(self, pos):
        company = self.company_id
        branch = pos.branch_id
        return {
            "issuer_nit": (company.vat or "").strip(),
            "issuer_name": company.name[:200],
            "municipality": branch.municipality,
            "phone": branch.phone or None,
            "branch_code": branch.code,
            "address": branch.address,
            "pos_code": pos.code,
            "user": (self.env.user.login or "usuario")[:100],
        }

    # ---- contrato interno de emisión -------------------------------------
    def _mira_siat_contract(self, pos):
        """Traduce la venta al contrato interno de emisión, con Decimal y con
        los códigos tomados de los catálogos sincronizados del contribuyente."""
        self.ensure_one()
        if self.state != "posted" or self.move_type not in FISCAL_MOVE_TYPES:
            raise UserError(_(
                "Solo se emite una factura o nota de crédito de cliente publicada."))
        if self.move_type == "out_refund":
            return self._mira_siat_note_contract(pos)
        company = self.company_id
        partner = self.commercial_partner_id
        identity = partner._mira_siat_fiscal_identity(company)
        method = self._mira_siat_resolve_payment_method()
        card = self.mira_siat_card_number or None
        if method.includes_card and not card:
            raise UserError(_("El método de pago exige el número de tarjeta."))
        currency_code, rate = self._mira_siat_currency()
        lines = self._mira_siat_lines(rate)
        sector = int(self.mira_siat_sector or company.mira_siat_default_sector)
        self._mira_siat_check_sector(sector, lines)

        items_total = sum(line["subtotal"] for line in lines)
        total_currency = money(self.amount_total)
        total = money(total_currency * rate)
        additional = items_total - total
        if rate != 1 and abs(additional) <= Decimal("0.01") * len(lines):
            # Diferencia de redondeo por conversión: manda la suma de ítems.
            total, additional = items_total, Decimal("0")
        if additional < 0:
            raise UserError(_(
                "El total fiscal (%(fiscal)s) no coincide con el total de la venta "
                "(%(sale)s). El SIN exige precios con impuesto incluido y 2 decimales; "
                "revise precios, descuentos e impuestos de las líneas.",
                fiscal=fmt(items_total), sale=fmt(total)))
        if total <= 0:
            raise UserError(_("El monto total de la factura debe ser mayor a cero."))
        gift = money(self.mira_siat_gift_card_amount) if method.includes_gift_card else None
        if gift is not None and not 0 < gift <= total:
            raise UserError(_(
                "El monto de gift card debe ser mayor a cero y no superar el total."))
        is_reserved = identity["number"] in constants.RESERVED_NITS
        contract = self._mira_siat_header(pos)
        contract.update({
            "sector_code": sector,
            "joint_nit": (self.mira_siat_joint_nit or None)
            if sector == constants.SECTOR_TELECOM else None,
            "customer_name": identity["name"][:500],
            "customer_doc_type": identity["doc_type"],
            "customer_doc_number": identity["number"][:20],
            "customer_complement": identity["complement"],
            "customer_code": (partner.ref or "C%s" % partner.id)[:100],
            "payment_method_code": int(method.code),
            "payment_method_name": method.name,
            "card_number": card if method.includes_card else None,
            "amount_total": total,
            "amount_subject_to_vat": total - (gift or Decimal("0")),
            "currency_code": currency_code,
            "exchange_rate": rate,
            "amount_total_currency": total_currency if rate != 1 else total,
            "gift_card_amount": gift,
            "additional_discount": additional if additional > 0 else None,
            "exception_code": 1 if (
                self.mira_siat_force_invalid_nit and not is_reserved
                and identity["doc_type"] == constants.DOC_TYPE_NIT) else None,
            "cafc": None,
            "legend": self._mira_siat_legend(lines[0]["activity_code"]),
            "lines": lines,
        })
        if contract["joint_nit"] and not contract["joint_nit"].isdigit():
            raise UserError(_("El NIT conjunto debe ser numérico."))
        return contract

    def _mira_siat_note_contract(self, pos):
        """Nota de Crédito-Débito: devuelve ítems de una factura ya aceptada."""
        self.ensure_one()
        origin = self.reversed_entry_id
        original = origin.mira_siat_invoice_ids.filtered(
            lambda d: d.state in ACCEPTED_BY_SIN
            and d.sector_code in constants.INVOICE_SECTORS)[:1]
        if not original:
            raise UserError(_(
                "La nota de crédito debe nacer de una factura ya aceptada por el SIN. "
                "Créela con el botón «Nota de crédito» de esa factura."))
        source = original.payload or {}
        if dec(source.get("exchange_rate", "1")) != 1:
            raise UserError(_(
                "Esta versión no emite notas sobre facturas en moneda extranjera."))
        originals = [dict(line, transaction_code=1) for line in source.get("lines", [])]
        available = {index: dec(line["quantity"]) for index, line in enumerate(originals)}
        returned = []
        for line in self._mira_siat_lines():
            match = next((
                index for index, orig in enumerate(originals)
                if index in available
                and orig["product_code"] == line["product_code"]
                and dec(orig["unit_price"]) == line["unit_price"]
                and available[index] >= line["quantity"]), None)
            if match is None:
                raise UserError(_(
                    "«%(line)s» no coincide con ningún ítem de la factura original (mismo "
                    "producto y precio, y cantidad no mayor a la facturada).",
                    line=line["description"]))
            del available[match]
            returned.append(dict(line, transaction_code=2))
        amount_returned = sum(line["subtotal"] for line in returned)
        contract = self._mira_siat_header(pos)
        contract.update({
            "sector_code": constants.SECTOR_CREDIT_DEBIT_NOTE,
            "customer_name": source["customer_name"],
            "customer_doc_type": source["customer_doc_type"],
            "customer_doc_number": source["customer_doc_number"],
            "customer_complement": source.get("customer_complement"),
            "customer_code": source["customer_code"],
            "original_invoice_id": original.id,
            "original_number": original.number,
            "original_cuf": original.cuf,
            "original_emission_iso": original.emission_iso,
            "amount_original": dec(source["amount_total"]),
            "amount_returned": amount_returned,
            "amount_total": amount_returned,
            "amount_discount": None,
            "amount_effective": money(amount_returned * Decimal(constants.VAT_RATE)),
            "exception_code": source.get("exception_code"),
            "legend": self._mira_siat_legend(returned[0]["activity_code"]),
            "lines": originals + returned,
        })
        return contract

    def _mira_siat_idempotency_key(self):
        """Estable para la misma venta: un doble clic o un reintento devuelven
        el mismo documento. Solo cambia tras un rechazo del SIN (nuevo intento)."""
        self.ensure_one()
        attempt = 1 + len(self.mira_siat_invoice_ids.filtered(lambda d: d.state == "rejected"))
        return "c%s-move%s-issue-v%s" % (self.company_id.id, self.id, attempt)

    # ---- botones ----------------------------------------------------------
    def action_mira_siat_issue(self):
        self.ensure_one()
        invoice = self.env["mira.siat.invoice"]._issue(
            self, self._mira_siat_idempotency_key())
        messages = {
            "valid": (_("Documento ACEPTADO por el SIN."), "success"),
            "offline_issued": (_("Emitido FUERA DE LÍNEA (contingencia). Se enviará "
                                 "por paquete."), "warning"),
            "pending_retry": (_("El SIN no respondió. NO vuelva a emitir: el documento "
                                "quedó pendiente y se consultará su estado."), "warning"),
            "rejected": (_("El SIN RECHAZÓ el documento. Revise los mensajes."), "danger"),
        }
        text, kind = messages.get(invoice.state, (_("Documento en proceso."), "info"))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": invoice.name, "message": text, "type": kind,
                       "sticky": kind != "success",
                       "next": {"type": "ir.actions.act_window_close"}},
        }

    def action_mira_siat_open(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Documentos fiscales"),
            "res_model": "mira.siat.invoice",
            "view_mode": "list,form",
            "domain": [("move_id", "=", self.id)],
        }
