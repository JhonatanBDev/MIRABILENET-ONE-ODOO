from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    mirabilenet_cot_delivery_ids = fields.One2many("mirabilenet.cot.delivery", "order_id",
                                                   string="Envíos por WhatsApp")
    mirabilenet_cot_customer_whatsapp = fields.Char(
        string="WhatsApp del cliente (cotización)", copy=False,
        help="A dónde se le envía la cotización. Vacío: el WhatsApp o el teléfono del contacto.")

    def _mirabilenet_cot_customer_number(self):
        self.ensure_one()
        partner = self.partner_id
        return (self.mirabilenet_cot_customer_whatsapp
                or ("mirabilenet_whatsapp" in partner._fields and partner.mirabilenet_whatsapp)
                or partner.phone or "")

    def _mirabilenet_cot_has_alerts(self):
        """Alertas que impiden que la cotización salga sola: las generales (sin stock, NVR
        que no alcanza…) y las de los equipos (precio antiguo). Un material cotizado con su
        precio de referencia no la frena: ese precio lo definió la empresa."""
        self.ensure_one()
        equipment = self.order_line.filtered(lambda l: l.mirabilenet_cot_group == "equipos")
        return bool(self.mirabilenet_cot_alerts
                    or any(equipment.mapped("mirabilenet_cot_alerts")))

    def _mirabilenet_cot_send_to_user(self, user, with_button=False):
        """El PDF al trabajador, para que lo revise y decida enviarlo."""
        self.ensure_one()
        if not user.mirabilenet_whatsapp:
            return self.env["mirabilenet.cot.delivery"], _("%s no tiene WhatsApp cargado.",
                                                           user.name)
        return self.env["mirabilenet.cot.delivery"]._queue(
            self, "trabajador", user.mirabilenet_whatsapp, user=user,
            with_button=with_button and bool(self._mirabilenet_cot_customer_number()))

    def _mirabilenet_cot_send_to_customer(self, user=None):
        """Aprueba si hace falta (quien cotiza, aprueba) y la deja en cola hacia el cliente."""
        self.ensure_one()
        number = self._mirabilenet_cot_customer_number()
        if not number:
            return self.env["mirabilenet.cot.delivery"], _("El cliente no tiene WhatsApp.")
        if self.mirabilenet_cot_stage == "borrador":
            self.with_user(user or self.env.user).sudo().action_mirabilenet_cot_approve()
        if self.mirabilenet_cot_stage not in ("aprobada", "enviada"):
            return self.env["mirabilenet.cot.delivery"], _(
                "La cotización %s ya está cerrada.", self.name)
        return self.env["mirabilenet.cot.delivery"]._queue(self, "cliente", number,
                                                           user=user or self.env.user)

    # -- botones del formulario ----------------------------------------
    def _mirabilenet_cot_notify(self, delivery, error, message):
        if error:
            raise UserError(error)
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"title": _("WhatsApp"), "type": "success", "message": message}}

    def action_mirabilenet_cot_whatsapp_me(self):
        self.ensure_one()
        self._mirabilenet_check_quote()
        delivery, error = self._mirabilenet_cot_send_to_user(self.env.user)
        return self._mirabilenet_cot_notify(delivery, error, _("Se le envía el PDF a su WhatsApp."))

    def action_mirabilenet_cot_whatsapp_customer(self):
        self.ensure_one()
        self._mirabilenet_check_quote()
        delivery, error = self._mirabilenet_cot_send_to_customer()
        return self._mirabilenet_cot_notify(delivery, error,
                                            _("La cotización sale al WhatsApp del cliente."))
