import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

EVENTS = [
    ("aviso_emitido", "Aviso de cobro emitido"),
    ("recordatorio_pago", "Recordatorio antes del vencimiento"),
    ("aviso_vencido", "Aviso de cobro vencido"),
    ("recordatorio_mora", "Recordatorio de deuda vencida"),
    ("comprobante_verificado", "Comprobante verificado"),
    ("comprobante_rechazado", "Comprobante rechazado"),
    ("comprobante_recibido", "Comprobante recibido"),
    # Declarados, todavía sin gancho: se guardan en cada mensaje enviado, así que
    # agregarlos después no debe cambiar el histórico.
    ("pago_recibido", "Pago recibido"),
    ("corte_programado", "Corte programado"),
    ("servicio_suspendido", "Servicio suspendido"),
    ("servicio_reactivado", "Servicio reactivado"),
    ("incidencia_masiva", "Incidencia o mantenimiento"),
    ("servicio_reparado", "Servicio reparado tras una avería"),
]
#: Eventos con gancho vivo. Los demás se rechazan al encolar.
ACTIVE_EVENTS = frozenset({
    "aviso_emitido", "recordatorio_pago", "aviso_vencido", "recordatorio_mora",
    "comprobante_verificado", "comprobante_rechazado", "comprobante_recibido",
    "servicio_reparado"})
#: Lista blanca cerrada de lo que una plantilla puede pedir. La plantilla nombra claves de
#: aquí, nunca rutas de campos.
VARIABLES = {
    "cliente": "Nombre o razón social del cliente",
    "codigo_cliente": "Código interno del cliente",
    "numero_aviso": "Número del aviso de cobro",
    "concepto": "Concepto del aviso",
    "periodo": "Período facturado, por ejemplo 08/2026",
    "monto": "Monto total con dos decimales",
    "saldo": "Saldo pendiente con dos decimales",
    "moneda": "Moneda del aviso, por ejemplo BOB",
    "fecha_vencimiento": "Fecha de vencimiento en formato dd/mm/aaaa",
    "dias_restantes": "Días que faltan para el vencimiento",
    "dias_vencido": "Días transcurridos desde el vencimiento",
    "sucursal": "Nombre de la sucursal que atiende al cliente",
    "telefono_sucursal": "Teléfono de la sucursal",
    "url_qr": "Dirección pública del QR de pago de la región",
}


class MirabilenetWhatsappTemplate(models.Model):
    """Plantilla aprobada en Meta, atada a un evento. Aquí solo va su nombre y el orden de
    sus variables: el texto vive en Meta."""
    _name = "mirabilenet.whatsapp.template"
    _description = "MIRABILENET: plantilla de WhatsApp"
    _order = "event, region_id"
    _rec_name = "meta_name"

    event = fields.Selection(EVENTS, string="Evento", required=True, index=True)
    region_id = fields.Many2one(
        "mirabilenet.region", string="Región", ondelete="cascade", index=True,
        help="Vacío = plantilla por defecto para todas las regiones.")
    meta_name = fields.Char(string="Nombre en Meta", required=True,
                            help="Nombre exacto de la plantilla aprobada, en minúsculas.")
    language = fields.Char(string="Idioma", default="es", required=True)
    parameter_format = fields.Selection(
        [("POSITIONAL", "Posicional ({{1}}, {{2}}...)"),
         ("NAMED", "Nombrado ({{cliente}}, {{monto}}...)")],
        string="Formato de parámetros", default="POSITIONAL", required=True)
    variables = fields.Char(
        string="Variables del cuerpo",
        help="Claves separadas por coma, en el orden de la plantilla. Disponibles: "
             + ", ".join(VARIABLES) + ".")
    reference_text = fields.Text(string="Texto de referencia",
                                 help="Copia del texto aprobado, solo para consulta.")
    qr_header = fields.Boolean(string="Imagen QR en el encabezado",
                               help="La plantilla de Meta debe tener encabezado de imagen.")
    active = fields.Boolean(string="Activa", default=True)

    def _variable_list(self):
        self.ensure_one()
        return [name.strip() for name in (self.variables or "").split(",") if name.strip()]

    @api.constrains("variables", "parameter_format")
    def _check_variables(self):
        for template in self:
            names = template._variable_list()
            unknown = [name for name in names if name not in VARIABLES]
            if unknown:
                raise ValidationError(_("Claves no reconocidas: %s.", ", ".join(unknown)))
            if template.parameter_format == "NAMED" and any(
                    not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) for name in names):
                raise ValidationError(_(
                    "Los nombres NAMED deben ser identificadores ASCII simples."))

    @api.constrains("event", "region_id", "active")
    def _check_unique(self):
        for template in self.filtered("active"):
            if self.search_count([
                    ("event", "=", template.event), ("region_id", "=", template.region_id.id),
                    ("active", "=", True), ("id", "!=", template.id)]):
                raise ValidationError(_(
                    "Ya hay una plantilla activa para ese evento y esa región."))

    @api.model
    def _for(self, event, region):
        """La plantilla de la región, o la de por defecto si la región no tiene."""
        Template = self.sudo()
        return (Template.search([("event", "=", event), ("region_id", "=", region.id)], limit=1)
                or Template.search([("event", "=", event), ("region_id", "=", False)], limit=1))
