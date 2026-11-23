"""El personal cotiza por WhatsApp: «cotiza casa 4 cámaras para Juan 7xxxxxxx». n8n (flujo
«20 Personal») entiende el pedido; Odoo arma la cotización con el motor y le manda el PDF."""
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.mirabilenet_whatsapp.whatsapp import content, phones

from .mirabilenet_cot_delivery import PAYLOAD_PREFIX

SEND_RE = re.compile(r"\benv[ií]\w*\b.*?\b(COT-\d{4}-\d+)\b", re.I)
COT_KINDS = [("cotizacion_revisar", "Cotización del bot por revisar (aviso al vendedor)")]


class MirabilenetStaffTemplate(models.Model):
    _inherit = "mirabilenet.staff.template"

    kind = fields.Selection(selection_add=COT_KINDS, ondelete={"cotizacion_revisar": "cascade"})


class MirabilenetStaffNotice(models.Model):
    _inherit = "mirabilenet.staff.notice"

    kind = fields.Selection(selection_add=COT_KINDS, ondelete={"cotizacion_revisar": "cascade"})

    @api.model
    def _handle_incoming(self, user, kind, text, data, external_id=""):
        """Antes que lo demás: el botón «Enviar al cliente» y el texto «enviar COT-…»."""
        option = (data or {}).get("opcion_id") or ""
        order = self.env["sale.order"]
        if kind == "respuesta" and option.startswith(PAYLOAD_PREFIX + ":"):
            parts = option.split(":")
            if len(parts) == 3 and parts[1].isdigit() and parts[2] == "enviar":
                order = order.sudo().browse(int(parts[1])).exists()
            if not order:
                self._reply(user.sudo(), _("Ese botón ya no corresponde a una cotización."))
                return "boton_invalido"
        else:
            match = SEND_RE.search(text or "")
            if match:
                order = order.sudo().search([("name", "=ilike", match.group(1)),
                                             ("mirabilenet_cot_is_quote", "=", True)], limit=1)
                if not order:
                    self._reply(user.sudo(), _("No encuentro la cotización %s.", match.group(1)))
                    return "cotizacion_desconocida"
        if not order:
            return super()._handle_incoming(user, kind, text, data, external_id)
        user = user.sudo()
        if order.mirabilenet_cot_requester_id != user and not user.has_group(
                "mirabilenet_cotizador.group_mirabilenet_cot_manager"):
            self._reply(user, _("La cotización %s la armó otra persona.", order.name))
            return "cotizacion_ajena"
        _delivery, error = order._mirabilenet_cot_send_to_customer(user)
        self._reply(user, error or _("Listo: %(n)s sale al WhatsApp de %(c)s.", n=order.name,
                                     c=order.partner_id.name))
        return "cotizacion_error" if error else "cotizacion_enviada"


class MirabilenetStaffInbox(models.Model):
    _inherit = "mirabilenet.staff.inbox"

    def _enqueue(self, user, text, external_id=""):
        """A n8n le hacen falta los kits y las ciudades para entender «cotiza…»."""
        record = super()._enqueue(user, text, external_id)
        if user.sudo().has_group("mirabilenet_cotizador.group_mirabilenet_cot_user"):
            kits = self.env["mirabilenet.cot.kit"].sudo().search([])
            record.payload = dict(
                record.payload or {},
                kits=[{"codigo": k.code, "nombre": k.name, "camaras": k.cameras} for k in kits],
                ciudades=self.env["mirabilenet.cot.city"].sudo().search([]).mapped("name"))
        return record

    @api.model
    def _apply_result(self, data):
        """Acción nueva de n8n: {mensaje_id, accion: "cotizar", kit?, pedido?, ciudad?,
        cliente_nombre, cliente_telefono?, con_factura?}."""
        if (data.get("accion") or "") != "cotizar":
            return super()._apply_result(data)
        record = self.sudo().browse(int(data.get("mensaje_id") or 0)).exists()
        if not record:
            return 404, {"detail": "Mensaje desconocido."}
        user = record.user_id
        Notice = self.env["mirabilenet.staff.notice"]

        def fail(code, text):
            Notice._reply(user, text)
            record.state = "atendido"
            return 200, {"ok": False, "resultado": code, "detail": text}

        if not user.has_group("mirabilenet_cotizador.group_mirabilenet_cot_user"):
            return fail("sin_permiso", _("Su usuario no tiene permiso para cotizar."))
        name = content.clean_text(data.get("cliente_nombre"), 120)
        kit_code = content.clean_text(data.get("kit"), 60)
        request_text = content.clean_text(data.get("pedido"), 600)
        if len(name) < 2:
            return fail("falta_cliente", _("¿Para quién es la cotización? Escriba el nombre del "
                                           "cliente (y su WhatsApp, si quiere enviársela)."))
        if not kit_code and not request_text:
            return fail("falta_pedido", _("¿Qué cotizo? Por ejemplo: «cotiza 4 cámaras para "
                                          "casa, 15 días, para Juan Pérez 70000000»."))
        city = self.env["mirabilenet.n8n.api"].sudo()._cot_city(data.get("ciudad"))
        phone = False
        if data.get("cliente_telefono"):
            try:
                phone = phones.normalize_number(data.get("cliente_telefono"))
            except phones.NotSendable:
                phone = False
        Partner = self.env["res.partner"].sudo()
        partner = Partner.search([("phone", "=", phone)], limit=1) if phone else Partner
        if not partner:
            vals = {"name": name, "phone": phone or False}
            if user.mirabilenet_region_id and "mirabilenet_region_id" in Partner._fields:
                vals["mirabilenet_region_id"] = user.mirabilenet_region_id.id
            partner = Partner.create(vals)
        Engine = self.env["mirabilenet.cot.engine"].sudo()
        invoice = data.get("con_factura")
        invoice = None if invoice is None else bool(invoice)
        kit = self.env["mirabilenet.cot.kit"].sudo().search(
            [("code", "=", kit_code)], limit=1) if kit_code else self.env["mirabilenet.cot.kit"]
        if not kit and not request_text:
            return fail("kit_desconocido", _("No conozco el kit «%s».", kit_code))
        try:
            with self.env.cr.savepoint():
                if kit:
                    order = Engine.create_from_kit(kit, city.name, partner, invoice=invoice,
                                                   origin="trabajador", requester=user,
                                                   notes=request_text or None)
                else:
                    order = Engine.create_from_text(request_text, city.name, partner,
                                                    invoice=invoice, origin="trabajador",
                                                    requester=user)
        except UserError as exc:
            return fail("no_se_pudo_cotizar", _("No pude cotizar: %s", str(exc)[:300]))
        if phone:
            order.mirabilenet_cot_customer_whatsapp = phone
        _delivery, error = order._mirabilenet_cot_send_to_user(user, with_button=True)
        lines = [_("Cotización %(n)s para %(c)s: %(m)s %(t)s.", n=order.name, c=partner.name,
                   m=order.currency_id.name or "Bs",
                   t=order.mirabilenet_cot_fmt(order.mirabilenet_cot_total))]
        if order._mirabilenet_cot_has_alerts():
            lines.append(_("Ojo, tiene alertas por revisar en el sistema antes de enviarla."))
        if error:
            lines.append(error)
        elif phone:
            lines.append(_("Le envío el PDF. Para mandársela al cliente, use el botón o escriba "
                           "«enviar %s».", order.name))
        else:
            lines.append(_("Le envío el PDF. No tengo el WhatsApp del cliente."))
        Notice._reply(user, "\n".join(lines))
        record.state = "atendido"
        return 200, {"ok": True, "resultado": "cotizacion", "numero": order.name,
                     "total": round(order.mirabilenet_cot_total, 2)}
