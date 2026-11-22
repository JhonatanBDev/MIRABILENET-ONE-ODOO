from odoo import fields, models, _
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    mirabilenet_region_id = fields.Many2one(related="config_id.mirabilenet_region_id",
                                            store=True, index=True, string="Región")
    mirabilenet_service_ids = fields.One2many("mirabilenet.service", "mirabilenet_pos_order_id",
                                              string="Servicios solicitados")

    def action_pos_order_paid(self):
        result = super().action_pos_order_paid()
        self._mirabilenet_request_services()
        return result

    def _mirabilenet_request_services(self):
        """Cada plan vendido en una sucursal es una solicitud de servicio: queda pendiente
        de instalación a nombre del cliente. Repetirlo no duplica."""
        Service = self.env["mirabilenet.service"].sudo()
        for order in self.sudo():
            branch = order.config_id.mirabilenet_branch_id
            plans = order.lines.mapped("product_id.product_tmpl_id").filtered(
                "mirabilenet_is_plan")
            if not branch or not plans or order.mirabilenet_service_ids:
                continue
            partner = order.partner_id
            if not partner:
                raise UserError(_(
                    "Para solicitar un servicio hay que elegir el cliente en la venta."))
            customer = {"mirabilenet_is_customer": True}
            if not partner.mirabilenet_region_id:
                customer["mirabilenet_region_id"] = branch.region_id.id
            if not partner.mirabilenet_branch_id and (
                    customer.get("mirabilenet_region_id") or partner.mirabilenet_region_id.id
            ) == branch.region_id.id:
                customer["mirabilenet_branch_id"] = branch.id
            partner.write(customer)
            if partner.mirabilenet_state == "prospecto":
                partner.mirabilenet_state = "instalacion_pendiente"
            for plan in plans:
                service = Service.create({
                    "partner_id": partner.id, "plan_id": plan.id,
                    "region_id": branch.region_id.id, "mirabilenet_pos_order_id": order.id,
                    "install_address": partner.street or False})
                self.env["mirabilenet.audit.log"]._log(
                    "crear", "Solicitud de servicio %s en la sucursal %s (venta %s)" % (
                        plan.name, branch.name, order.name),
                    record=service, region=branch.region_id, payload={"venta": order.id})
        return True
