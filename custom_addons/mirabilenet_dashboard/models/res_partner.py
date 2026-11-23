from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Para filtrar por plan, nodo o modalidad lo que cuelga del cliente (pagos, comprobantes,
    # casos). No se guarda: es la inversa de mirabilenet.service.partner_id.
    mirabilenet_service_ids = fields.One2many("mirabilenet.service", "partner_id",
                                              string="Servicios")
