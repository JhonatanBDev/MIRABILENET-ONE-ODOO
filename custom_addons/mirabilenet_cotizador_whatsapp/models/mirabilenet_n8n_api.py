"""Herramientas del cotizador para los flujos de n8n (bots de ventas y de soporte).

La IA solo elige el kit o transcribe el pedido: los productos, los precios y el margen los pone
el motor del cotizador. Una cotización con alertas no sale sola."""
import logging
import uuid

from odoo import api, models
from odoo.exceptions import UserError

from odoo.addons.mirabilenet_whatsapp.whatsapp.content import SendRejected
from odoo.addons.mirabilenet_whatsapp.whatsapp import content

_logger = logging.getLogger(__name__)
MAX_PRODUCTS = 8


class MirabilenetN8nApi(models.AbstractModel):
    _inherit = "mirabilenet.n8n.api"

    # ------------------------------------------------------------------
    @api.model
    def _cot_city(self, name):
        City = self.env["mirabilenet.cot.city"].sudo()
        name = content.clean_text(name, 60)
        city = City.search([("name", "=ilike", name)], limit=1) if name else City
        return city or City.search([("is_base", "=", True)], limit=1) or City.search([], limit=1)

    @api.model
    def _cot_currency(self):
        return self.env.company.currency_id.name or "BOB"

    @api.model
    def conversation_kits(self, pk):
        """Kits que el bot puede ofrecer. Sin precio: el precio sale al cotizar."""
        conversation = self._conversation(pk)
        if not conversation:
            return 404, {"detail": "Conversacion inexistente."}
        kits = self.env["mirabilenet.cot.kit"].sudo().search([("offer_bot", "=", True)])
        cities = self.env["mirabilenet.cot.city"].sudo().search([]).mapped("name")
        return 200, {
            "ciudades": cities,
            "kits": [{"codigo": k.code, "nombre": k.name, "camaras": k.cameras,
                      "tecnologia": k.technology or None, "gama": k.range_ or None,
                      "dias_de_grabacion": k.days} for k in kits]}

    @api.model
    def conversation_products(self, pk, params):
        """Equipos publicados para el bot, con el precio de venta que calcula el motor."""
        conversation = self._conversation(pk)
        if not conversation:
            return 404, {"detail": "Conversacion inexistente."}
        words = content.clean_text((params or {}).get("buscar"), 80)
        city = self._cot_city((params or {}).get("ciudad"))
        domain = [("mirabilenet_cot_offer_bot", "=", True), ("sale_ok", "=", True),
                  ("mirabilenet_cot_category", "!=", False)]
        for word in words.split()[:4]:
            domain += ["|", "|", ("name", "ilike", word), ("mirabilenet_cot_brand", "ilike", word),
                       ("mirabilenet_cot_category", "ilike", word)]
        products = self.env["product.template"].sudo().search(domain, limit=MAX_PRODUCTS)
        items = []
        for product in products:
            stock = product._mirabilenet_cot_stock_in(city.name) if city else None
            items.append({
                "codigo": product.mirabilenet_cot_sku or str(product.id),
                "nombre": product.name, "marca": product.mirabilenet_cot_brand or None,
                "categoria": product.mirabilenet_cot_category,
                "precio": round(product.mirabilenet_cot_price, 2),
                "precio_con_factura": round(product.mirabilenet_cot_price_invoiced, 2),
                "hay_en_la_ciudad": None if stock is None else stock > 0})
        return 200, {"ciudad": city.name or None, "moneda": self._cot_currency(),
                     "equipos": items}

    # ------------------------------------------------------------------
    @api.model
    def _cot_partner(self, conversation, name):
        """El cliente de la conversación, o un contacto nuevo para el interesado."""
        if conversation.partner_id:
            return conversation.partner_id
        Partner = self.env["res.partner"].sudo()
        partner = Partner.search([("phone", "=", conversation.contact)], limit=1)
        if partner:
            return partner
        region = self._conversation_region(conversation)
        vals = {"name": name, "phone": conversation.contact,
                "comment": "Contacto creado por el bot al enviarle una cotización."}
        if region and "mirabilenet_region_id" in Partner._fields:
            vals["mirabilenet_region_id"] = region.id
        return Partner.create(vals)

    @api.model
    def _cot_sellers(self, conversation):
        """A quién se le avisa una cotización que no puede salir sola."""
        Users = self.env["res.users"].sudo()
        region = self._conversation_region(conversation)
        domain = [("mirabilenet_role", "=", "vendedor")]
        if region:
            domain.append(("mirabilenet_region_id", "=", region.id))
        sellers = Users.search(domain)._mirabilenet_reachable()
        return sellers or (Users._mirabilenet_region_supervisors(region) if region else Users)

    @api.model
    def conversation_quotation(self, pk, data):
        """Arma la cotización y, si no tiene alertas, le envía el PDF al contacto."""
        conversation = self._conversation(pk)
        if not conversation:
            return 404, {"detail": "Conversacion inexistente."}
        kit_code = content.clean_text(data.get("kit"), 60)
        request_text = content.clean_text(data.get("pedido"), 600)
        if not kit_code and not request_text:
            return 400, {"codigo": "falta_pedido",
                         "detail": "Indique un kit o escriba el pedido del cliente."}
        name = content.clean_text(data.get("nombre"), 120) or conversation.partner_id.name
        if len(name or "") < 2:
            return 400, {"codigo": "falta_nombre",
                         "detail": "Hace falta el nombre de la persona."}
        city = self._cot_city(data.get("ciudad"))
        if not city:
            return 409, {"codigo": "sin_ciudades", "detail": "El cotizador no tiene ciudades."}
        invoice = data.get("con_factura")
        invoice = None if invoice is None else bool(invoice)
        Engine = self.env["mirabilenet.cot.engine"].sudo()
        partner = self._cot_partner(conversation, name)
        try:
            with self.env.cr.savepoint():
                if kit_code:
                    kit = self.env["mirabilenet.cot.kit"].sudo().search(
                        [("code", "=", kit_code), ("offer_bot", "=", True)], limit=1)
                    if not kit:
                        return 404, {"codigo": "kit_desconocido",
                                     "detail": "Ese kit no existe. Consulte los kits."}
                    order = Engine.create_from_kit(kit, city.name, partner, invoice=invoice,
                                                   origin="bot", notes=request_text or None)
                else:
                    order = Engine.create_from_text(request_text, city.name, partner,
                                                    invoice=invoice, origin="bot")
        except UserError as exc:
            return 409, {"codigo": "no_se_pudo_cotizar", "detail": str(exc)[:300]}
        order.mirabilenet_cot_customer_whatsapp = conversation.contact
        answer = {"numero": order.name, "moneda": order.currency_id.name,
                  "total": round(order.mirabilenet_cot_total, 2),
                  "con_factura": order.mirabilenet_cot_invoice, "ciudad": city.name,
                  "valida_hasta": order.validity_date.strftime("%d/%m/%Y")
                  if order.validity_date else None}
        if order._mirabilenet_cot_has_alerts():
            _logger.info("Cotización %s del bot con alertas, no sale sola: %s | %s", order.name,
                         order.mirabilenet_cot_alerts,
                         [x for x in order.order_line.mapped("mirabilenet_cot_alerts") if x])
            sellers = self._cot_sellers(conversation)
            self.env["mirabilenet.staff.notice"]._notify(
                sellers, "cotizacion_revisar",
                {"referencia": order.name, "cliente": partner.name}) if sellers else None
            order.message_post(body="El bot armó esta cotización con alertas: no se envió. "
                                    "Revísela, apruébela y envíela al cliente.")
            # El total no se le dice al contacto: todavía puede cambiar.
            return 202, {"enviada": False, "codigo": "requiere_asesor", "numero": order.name,
                         "detail": "La cotización necesita que un asesor la confirme (stock o "
                                   "precio por verificar). Dígale que un asesor se la envía."}
        order.action_mirabilenet_cot_approve()
        pdf, file_name = order._mirabilenet_cot_pdf()
        key = "cot:%d:%s" % (conversation.id, str(data.get("mensaje_id") or uuid.uuid4().hex))
        try:
            _message, created = conversation._enqueue_outgoing(
                "documento", {"texto": order._mirabilenet_cot_whatsapp_summary()[:1000]}, key,
                attachment={"content": pdf, "mime": "application/pdf", "name": file_name})
        except SendRejected as exc:
            return 409, {"codigo": exc.code, "detail": exc.detail, "numero": order.name}
        order.action_mirabilenet_cot_mark_sent()
        order.message_post(body="El bot envió esta cotización por WhatsApp.")
        return 201, dict(answer, enviada=True, duplicado=not created)
