from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MirabilenetCotWizard(models.TransientModel):
    """Nueva cotización: desde un kit plantilla o desde lo que pidió el cliente, escrito."""
    _name = "mirabilenet.cot.wizard"
    _description = "Cotizador: nueva cotización"

    partner_id = fields.Many2one("res.partner", string="Cliente", required=True)
    mode = fields.Selection([("kit", "Desde un kit"), ("texto", "Desde el pedido escrito")],
                            string="Cómo", default="kit", required=True)
    kit_id = fields.Many2one("mirabilenet.cot.kit", string="Kit")
    text = fields.Text(string="Pedido",
                       help="Como lo escribió el cliente, por ejemplo: «6 cámaras para mi tienda, "
                            "2 afuera, que graben 20 días».")
    city_id = fields.Many2one("mirabilenet.cot.city", string="Ciudad", required=True,
                              default=lambda self: self.env["mirabilenet.cot.city"].search(
                                  [("is_base", "=", True)], limit=1))
    invoice = fields.Boolean(string="Con factura (IVA + IT)",
                             default=lambda self: self.env["mirabilenet.cot.engine"]._param(
                                 "facturar_por_defecto") in ("1", "True", "true"))
    meters = fields.Float(string="Metros de cable (total)",
                          help="Vacío: los metros por cámara del kit.")
    km = fields.Float(string="Km adicionales", help="Fuera del radio urbano, ida y vuelta.")
    title = fields.Char(string="Título")

    @api.onchange("kit_id")
    def _onchange_kit_id(self):
        if self.kit_id and not self.title:
            self.title = self.kit_id.name

    def action_create(self):
        self.ensure_one()
        Engine = self.env["mirabilenet.cot.engine"]
        if self.mode == "kit":
            if not self.kit_id:
                raise UserError(_("Elija un kit."))
            order = Engine.create_from_kit(self.kit_id, self.city_id.name, self.partner_id,
                                           invoice=self.invoice, meters=self.meters or None,
                                           km=self.km, title=self.title or None)
        else:
            if not (self.text or "").strip():
                raise UserError(_("Escriba el pedido."))
            order = Engine.create_from_text(self.text, self.city_id.name, self.partner_id,
                                            invoice=self.invoice)
        return {"type": "ir.actions.act_window", "res_model": "sale.order", "res_id": order.id,
                "view_mode": "form", "target": "current"}
