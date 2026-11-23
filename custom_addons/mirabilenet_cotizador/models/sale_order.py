"""La cotización del cotizador es un sale.order con su propia etapa, precios congelados y los
totales de MIRABILENET (IVA + IT sobre el subtotal, según el modo con que se armó)."""
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..cotizador import precios
from .mirabilenet_cot_engine import ORIGINS

STAGES = [("borrador", "Borrador"), ("aprobada", "Aprobada"), ("enviada", "Enviada"),
          ("ganada", "Ganada"), ("perdida", "Perdida")]
GROUPS = [("equipos", "Equipos"), ("materiales", "Materiales"), ("mano_obra", "Mano de obra"),
          ("viaticos", "Viáticos")]


class SaleOrder(models.Model):
    _inherit = "sale.order"

    mirabilenet_cot_is_quote = fields.Boolean(string="Cotización del cotizador", index=True,
                                              copy=True)
    mirabilenet_cot_title = fields.Char(string="Título")
    mirabilenet_cot_stage = fields.Selection(STAGES, string="Etapa de la cotización",
                                             default="borrador", index=True, tracking=True,
                                             copy=False)
    mirabilenet_cot_origin = fields.Selection(ORIGINS, string="Origen", default="oficina")
    mirabilenet_cot_city_id = fields.Many2one("mirabilenet.cot.city", string="Ciudad")
    mirabilenet_cot_invoice = fields.Boolean(string="Con factura", default=True)
    mirabilenet_cot_rate = fields.Float(string="Tipo de cambio (Bs por USD)", digits=(12, 4),
                                        help="Congelado al armar la cotización.")
    mirabilenet_cot_tax_mode = fields.Selection([("agregar", "Se agregan al subtotal"),
                                                 ("bruto", "Incluidos (bruto)")],
                                                string="Impuestos", default="agregar")
    mirabilenet_cot_iva_rate = fields.Float(string="IVA", default=0.13, digits=(6, 4))
    mirabilenet_cot_it_rate = fields.Float(string="IT", default=0.03, digits=(6, 4))
    mirabilenet_cot_kit_id = fields.Many2one("mirabilenet.cot.kit", string="Kit")
    mirabilenet_cot_alerts = fields.Text(string="Alertas (internas)", copy=False)
    mirabilenet_cot_notes = fields.Text(string="Notas internas")
    mirabilenet_cot_storage = fields.Text(string="Cálculo de almacenamiento")
    mirabilenet_cot_requester_id = fields.Many2one("res.users", string="Cotizó")
    mirabilenet_cot_approved_by = fields.Many2one("res.users", string="Aprobó", copy=False,
                                                  readonly=True)
    mirabilenet_cot_approved_at = fields.Datetime(string="Aprobada el", copy=False, readonly=True)
    mirabilenet_cot_sent_at = fields.Datetime(string="Enviada el", copy=False, readonly=True)
    mirabilenet_cot_subtotal = fields.Monetary(string="Subtotal", compute="_compute_cot_totals",
                                               store=True)
    mirabilenet_cot_iva = fields.Monetary(string="IVA (13 %)", compute="_compute_cot_totals",
                                          store=True)
    mirabilenet_cot_it = fields.Monetary(string="IT (3 %)", compute="_compute_cot_totals",
                                         store=True)
    mirabilenet_cot_total = fields.Monetary(string="Total", compute="_compute_cot_totals",
                                            store=True)
    mirabilenet_cot_total_usd = fields.Float(string="Total en USD", compute="_compute_cot_totals",
                                             store=True, digits=(12, 2))
    mirabilenet_cot_cost = fields.Monetary(string="Costo (interno)", compute="_compute_cot_totals",
                                           store=True)
    mirabilenet_cot_profit = fields.Monetary(string="Ganancia (interna)",
                                             compute="_compute_cot_totals", store=True)

    @api.depends("order_line.price_subtotal", "order_line.mirabilenet_cot_cost",
                 "order_line.product_uom_qty", "mirabilenet_cot_invoice",
                 "mirabilenet_cot_tax_mode", "mirabilenet_cot_iva_rate", "mirabilenet_cot_it_rate",
                 "mirabilenet_cot_rate")
    def _compute_cot_totals(self):
        for order in self:
            lines = order.order_line.filtered(lambda l: not l.display_type)
            subtotal = sum(lines.mapped("price_subtotal"))
            cost = sum(l.mirabilenet_cot_cost * l.product_uom_qty for l in lines)
            cfg = precios.Config(iva=precios.D(order.mirabilenet_cot_iva_rate),
                                 it=precios.D(order.mirabilenet_cot_it_rate),
                                 modo_impuestos=order.mirabilenet_cot_tax_mode or "agregar")
            taxes = precios.calcular_impuestos(cfg, subtotal, order.mirabilenet_cot_invoice)
            order.mirabilenet_cot_subtotal = float(taxes.subtotal)
            order.mirabilenet_cot_iva = float(taxes.iva)
            order.mirabilenet_cot_it = float(taxes.it)
            order.mirabilenet_cot_total = float(taxes.total)
            order.mirabilenet_cot_total_usd = float(precios.a_usd(
                taxes.total, precios.TipoCambio(precios.D(order.mirabilenet_cot_rate or 0))))
            order.mirabilenet_cot_cost = cost
            order.mirabilenet_cot_profit = float(taxes.subtotal) - cost

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("mirabilenet_cot_is_quote") and vals.get("name", _("New")) in (
                    _("New"), "New", "/", False):
                vals["name"] = self.env["ir.sequence"].next_by_code("mirabilenet.cot.quote") \
                    or _("New")
        return super().create(vals_list)

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        for order, vals in zip(self, vals_list):
            if order.mirabilenet_cot_is_quote:
                vals["name"] = _("New")
                vals["mirabilenet_cot_stage"] = "borrador"
        return vals_list

    # ------------------------------------------------------------------
    # Etapas
    # ------------------------------------------------------------------
    def _mirabilenet_check_quote(self):
        for order in self:
            if not order.mirabilenet_cot_is_quote:
                raise UserError(_("%s no es una cotización del cotizador.", order.name))

    def action_mirabilenet_cot_approve(self):
        """Aprueba quien puede cotizar (decisión de MIRABILENET)."""
        self._mirabilenet_check_quote()
        for order in self:
            if order.mirabilenet_cot_stage != "borrador":
                raise UserError(_("Solo se aprueba un borrador."))
            if not order.order_line.filtered(lambda l: not l.display_type):
                raise UserError(_("La cotización no tiene líneas."))
            order.write({"mirabilenet_cot_stage": "aprobada",
                         "mirabilenet_cot_approved_by": self.env.user.id,
                         "mirabilenet_cot_approved_at": fields.Datetime.now()})
        return True

    def action_mirabilenet_cot_draft(self):
        self._mirabilenet_check_quote()
        for order in self:
            if order.mirabilenet_cot_stage not in ("aprobada", "enviada", "perdida"):
                raise UserError(_("Esa cotización no vuelve a borrador."))
            if order.state == "cancel":
                order.action_draft()
            order.mirabilenet_cot_stage = "borrador"
        return True

    def action_mirabilenet_cot_mark_sent(self):
        self._mirabilenet_check_quote()
        for order in self:
            if order.mirabilenet_cot_stage not in ("aprobada", "enviada"):
                raise UserError(_("Antes de enviarla hay que aprobarla."))
            order.write({"mirabilenet_cot_stage": "enviada",
                         "mirabilenet_cot_sent_at": fields.Datetime.now()})
        return True

    def action_mirabilenet_cot_won(self):
        """Ganada: se confirma como venta de Odoo."""
        self._mirabilenet_check_quote()
        for order in self:
            if order.mirabilenet_cot_stage not in ("aprobada", "enviada"):
                raise UserError(_("Solo se gana una cotización aprobada o enviada."))
            order.mirabilenet_cot_stage = "ganada"
            if order.state in ("draft", "sent"):
                order.action_confirm()
        return True

    def action_mirabilenet_cot_lost(self):
        self._mirabilenet_check_quote()
        for order in self:
            if order.mirabilenet_cot_stage == "ganada":
                raise UserError(_("Una cotización ganada no se pierde: cancele la venta."))
            order.mirabilenet_cot_stage = "perdida"
        return True

    def action_mirabilenet_cot_renew(self):
        """Renovar la vigencia: nueva fecha, los mismos precios."""
        self._mirabilenet_check_quote()
        days = int(self.env["mirabilenet.cot.engine"]._param("vigencia_dias") or 5)
        for order in self:
            order.validity_date = fields.Date.context_today(order) + timedelta(days=days)
        return True

    def action_mirabilenet_cot_duplicate(self):
        self._mirabilenet_check_quote()
        new = self.copy()
        return {"type": "ir.actions.act_window", "res_model": "sale.order", "res_id": new.id,
                "view_mode": "form", "target": "current"}

    def action_mirabilenet_cot_pdf(self):
        return self.env.ref("mirabilenet_cotizador.action_report_mirabilenet_cot").report_action(
            self)

    def _mirabilenet_cot_pdf(self):
        """El PDF del cliente (bytes) y su nombre de archivo."""
        self.ensure_one()
        pdf, _kind = self.env["ir.actions.report"].sudo()._render_qweb_pdf(
            "mirabilenet_cotizador.action_report_mirabilenet_cot", self.ids)
        return pdf, "%s.pdf" % self.name.replace("/", "-")

    def mirabilenet_cot_fmt(self, value, qty=False):
        """Número en formato boliviano: 1.234,56 (o la cantidad sin decimales de más)."""
        if qty:
            return ("%g" % (value or 0)).replace(".", ",")
        return "{:,.2f}".format(value or 0).replace(",", "X").replace(".", ",").replace("X", ".")

    def _mirabilenet_cot_whatsapp_summary(self):
        """Resumen corto para pegar en WhatsApp (sin datos internos)."""
        self.ensure_one()
        currency = self.currency_id.symbol or "Bs"
        lines = [_("*%(n)s* · %(t)s", n=self.name, t=self.mirabilenet_cot_title or ""),
                 _("Cliente: %s", self.partner_id.name)]
        for line in self.order_line.filtered(lambda l: not l.display_type and
                                             l.mirabilenet_cot_group == "equipos"):
            lines.append("• %s × %s" % (int(line.product_uom_qty) if line.product_uom_qty ==
                                       int(line.product_uom_qty) else line.product_uom_qty,
                                       line.name.split(" — ")[0]))
        lines.append(_("Total: %(c)s %(t)s%(f)s", c=currency,
                       t=self.mirabilenet_cot_fmt(self.mirabilenet_cot_total),
                       f=_(" (con factura)") if self.mirabilenet_cot_invoice else ""))
        if self.validity_date:
            lines.append(_("Válida hasta el %s", self.validity_date.strftime("%d/%m/%Y")))
        return "\n".join(lines)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    mirabilenet_cot_frozen = fields.Boolean(string="Precio congelado", copy=True)
    mirabilenet_cot_group = fields.Selection(GROUPS, string="Grupo")
    mirabilenet_cot_unit = fields.Char(string="Unidad (cotizador)")
    mirabilenet_cot_cost = fields.Float(string="Costo unitario (interno)")
    mirabilenet_cot_markup = fields.Float(string="Recargo % (interno)")
    mirabilenet_cot_stock = fields.Integer(string="Stock en la ciudad (interno)", default=-1,
                                           help="-1 = sin verificar.")
    mirabilenet_cot_reason = fields.Char(string="Por qué se eligió (interno)")
    mirabilenet_cot_alerts = fields.Text(string="Alertas (internas)")

    # Los precios de una cotización armada no cambian al abrirla, al cambiar la cantidad ni al
    # duplicarla: lo que se le ofreció al cliente se respeta.
    def _compute_price_unit(self):
        return super(SaleOrderLine, self.filtered(
            lambda l: not l.mirabilenet_cot_frozen))._compute_price_unit()

    def _compute_tax_ids(self):
        frozen = self.filtered("mirabilenet_cot_frozen")
        frozen.tax_ids = False
        return super(SaleOrderLine, self - frozen)._compute_tax_ids()

    def _compute_name(self):
        return super(SaleOrderLine, self.filtered(
            lambda l: not l.mirabilenet_cot_frozen))._compute_name()

    def write(self, vals):
        if not self.env.context.get("mirabilenet_cot_force"):
            locked = self.filtered(lambda l: l.order_id.mirabilenet_cot_is_quote
                                   and l.order_id.mirabilenet_cot_stage != "borrador")
            if locked and set(vals) & {"product_uom_qty", "price_unit", "name", "product_id",
                                       "mirabilenet_cot_markup"}:
                raise UserError(_("Solo se edita una cotización en borrador."))
        if "mirabilenet_cot_markup" in vals and "price_unit" not in vals:
            # Recargo cambiado a mano: precio nuevo con el redondeo, dentro de los topes.
            engine = self.env["mirabilenet.cot.engine"]
            cfg = engine._config()
            for line in self.filtered(lambda l: l.mirabilenet_cot_cost):
                markup = precios.D(vals["mirabilenet_cot_markup"]) / 100
                try:
                    precios.validar_recargo(cfg, markup, precios.D(line.mirabilenet_cot_cost))
                except ValueError as exc:
                    raise UserError(str(exc)) from exc
                super(SaleOrderLine, line).write(dict(vals, price_unit=float(
                    precios.precio_venta(cfg, precios.D(line.mirabilenet_cot_cost), markup))))
            others = self.filtered(lambda l: not l.mirabilenet_cot_cost)
            return super(SaleOrderLine, others).write(vals) if others else True
        return super().write(vals)
