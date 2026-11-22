from odoo import fields, models

FAQ_CATEGORIES = [("servicio", "Servicio de internet"), ("instalacion", "Instalación"),
                  ("pagos", "Pagos y facturación"), ("camaras", "Cámaras"),
                  ("soporte", "Soporte")]


class MirabilenetWebFaq(models.Model):
    _name = "mirabilenet.web.faq"
    _description = "MIRABILENET: pregunta frecuente"
    _inherit = ["mirabilenet.web.published"]
    _order = "sequence, id"
    _rec_name = "question"

    question = fields.Char(string="Pregunta", required=True, size=200)
    answer = fields.Text(string="Respuesta", required=True)
    category = fields.Selection(FAQ_CATEGORIES, string="Categoría", default="servicio",
                                required=True)
    sequence = fields.Integer(string="Orden", default=0)
    active = fields.Boolean(string="Activa", default=True)
