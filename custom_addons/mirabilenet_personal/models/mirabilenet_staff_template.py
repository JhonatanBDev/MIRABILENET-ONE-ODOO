from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

#: Avisos al personal. Cada uno necesita una plantilla aprobada en Meta, porque se le escribe
#: primero a la persona (fuera de la ventana de 24 horas).
KINDS = [
    ("averia_asignada", "Avería asignada al técnico"),
    ("averia_recordatorio", "Recordatorio de avería sin atender"),
    ("averia_resuelta", "Avería resuelta (aviso a los demás técnicos)"),
    ("averia_no_resuelta", "Avería no resuelta (aviso al jefe)"),
    ("averia_sin_atender", "Avería sin atender (aviso al jefe)"),
    ("tarea_asignada", "Tarea asignada"),
]
#: Lo que cada aviso puede poner en su plantilla, por nombre. El texto vive en Meta.
VARIABLES = {
    "persona": "Nombre de quien recibe el aviso",
    "tecnico": "Técnico de la avería",
    "referencia": "Número de la avería",
    "cliente": "Cliente",
    "telefono": "Teléfono del cliente",
    "direccion": "Dirección de instalación",
    "caja": "Caja NAP",
    "puerto": "Puerto de la caja",
    "vecinos": "Diagnóstico de la caja (averías de los vecinos)",
    "mapa": "Link de Google Maps a la caja",
    "nota": "Nota del técnico",
    "horas": "Horas sin atender",
    "pendientes_caja": "Averías que siguen abiertas en esa caja",
    "pendientes_zona": "Averías que siguen abiertas en la zona",
    "tarea": "Nombre de la tarea",
    "proyecto": "Proyecto de la tarea",
    "fecha_limite": "Fecha límite de la tarea",
    "asignado_por": "Quién asignó la tarea",
}
#: Botones de respuesta rápida: lo que hace cada uno.
ACTIONS = {
    "en_camino": "Voy en camino",
    "arreglado": "Arreglado",
    "no_resuelto": "No se pudo",
    "recibido": "Recibido",
    "terminada": "Terminada",
}


class MirabilenetStaffTemplate(models.Model):
    """Plantilla de Meta para un aviso al personal: su nombre, el orden de sus variables y,
    si tiene, el orden de sus botones."""
    _name = "mirabilenet.staff.template"
    _description = "MIRABILENET: plantilla de aviso al personal"
    _order = "kind"
    _rec_name = "meta_name"

    kind = fields.Selection(KINDS, string="Aviso", required=True)
    meta_name = fields.Char(string="Nombre en Meta", required=True)
    language = fields.Char(string="Idioma", default="es", required=True)
    variables = fields.Char(string="Variables, en orden",
                            help="Separadas por coma, como están {{1}}, {{2}}… en Meta.")
    buttons = fields.Char(string="Botones, en orden",
                          help="Acciones de los botones de respuesta rápida, separadas por coma.")
    active = fields.Boolean(default=True)

    _kind_uniq = models.Constraint("unique(kind)", "Ya hay una plantilla para ese aviso.")

    def _variable_list(self):
        self.ensure_one()
        return [v.strip() for v in (self.variables or "").split(",") if v.strip()]

    def _button_list(self):
        self.ensure_one()
        return [b.strip() for b in (self.buttons or "").split(",") if b.strip()]

    @api.constrains("variables", "buttons")
    def _check_names(self):
        for template in self:
            unknown = [v for v in template._variable_list() if v not in VARIABLES]
            if unknown:
                raise ValidationError(_("Variables desconocidas: %s", ", ".join(unknown)))
            unknown = [b for b in template._button_list() if b not in ACTIONS]
            if unknown:
                raise ValidationError(_("Botones desconocidos: %s", ", ".join(unknown)))

    @api.model
    def _for(self, kind):
        return self.sudo().search([("kind", "=", kind)], limit=1)
