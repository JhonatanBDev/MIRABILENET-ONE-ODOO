from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

CUSTOMER_MANAGER = "mirabilenet_isp.group_mirabilenet_customer_manager"
#: Quien atiende servicios (técnico, NOC) puede mantener los contactos de un cliente,
#: pero no al cliente.
CONTACT_MANAGER = "mirabilenet_isp.group_mirabilenet_service_manager"

CUSTOMER_TYPES = [
    ("residencial", "Residencial"),
    ("empresarial", "Empresarial"),
    ("comunidad", "Comunidad"),
    ("institucion", "Institución"),
    ("mina", "Mina"),
]
STATES = [
    ("prospecto", "Prospecto"),
    ("evaluacion", "Evaluación"),
    ("cotizado", "Cotizado"),
    ("instalacion_pendiente", "Instalación pendiente"),
    ("activo", "Activo"),
    ("moroso", "Moroso"),
    ("suspendido", "Suspendido"),
    ("reactivado", "Reactivado"),
    ("baja_solicitada", "Baja solicitada"),
    ("cancelado", "Cancelado"),
]
#: Transiciones permitidas del estado comercial.
TRANSITIONS = {
    "prospecto": {"evaluacion", "cancelado"},
    "evaluacion": {"cotizado", "cancelado"},
    "cotizado": {"instalacion_pendiente", "cancelado"},
    "instalacion_pendiente": {"activo", "cancelado"},
    "activo": {"moroso", "baja_solicitada", "suspendido"},
    "moroso": {"suspendido", "activo", "baja_solicitada"},
    "suspendido": {"reactivado", "baja_solicitada", "cancelado"},
    "reactivado": {"activo", "moroso"},
    "baja_solicitada": {"cancelado", "activo"},
    "cancelado": set(),
}
#: Escrituras técnicas de Odoo que no son editar al cliente.
TECHNICAL_PREFIXES = ("message_", "activity_")


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "mirabilenet.region.scoped"]
    _region_path = ("mirabilenet_region_id", "mirabilenet_is_customer", "parent_id")

    mirabilenet_is_customer = fields.Boolean(string="Es cliente de MIRABILENET", index=True)
    mirabilenet_code = fields.Char(string="Código de cliente", copy=False, readonly=True,
                                   index=True)
    mirabilenet_customer_type = fields.Selection(
        CUSTOMER_TYPES, string="Tipo de cliente", default="residencial")
    mirabilenet_region_id = fields.Many2one(
        "mirabilenet.region", string="Región", ondelete="restrict", index=True, tracking=True)
    mirabilenet_zone_id = fields.Many2one(
        "mirabilenet.zone", string="Zona", ondelete="set null",
        domain="[('region_id', '=', mirabilenet_region_id)]")
    mirabilenet_branch_id = fields.Many2one(
        "mirabilenet.branch", string="Sucursal", ondelete="set null",
        domain="[('region_id', '=', mirabilenet_region_id)]")
    mirabilenet_state = fields.Selection(
        STATES, string="Estado comercial", default="prospecto", copy=False, index=True,
        tracking=True, help="Cambia con los botones, no editando el campo.")
    mirabilenet_whatsapp = fields.Char(string="WhatsApp")
    mirabilenet_contact_verified = fields.Boolean(string="Contacto verificado")
    mirabilenet_requires_invoice = fields.Boolean(string="Requiere factura")
    # En los contactos de un cliente.
    mirabilenet_authorized_support = fields.Boolean(string="Autorizado para soporte",
                                                    default=True)
    mirabilenet_authorized_payments = fields.Boolean(string="Autorizado para pagos")

    # Lo que usan las reglas de registro: el cliente y también sus contactos.
    mirabilenet_restricted = fields.Boolean(
        string="Dato de cliente", compute="_compute_mirabilenet_scope", store=True, index=True)
    mirabilenet_scope_region_id = fields.Many2one(
        "mirabilenet.region", string="Región de alcance",
        compute="_compute_mirabilenet_scope", store=True, index=True)

    _mirabilenet_code_uniq = models.Constraint(
        "unique(mirabilenet_code)", "Ya existe un cliente con ese código.")

    @api.depends("commercial_partner_id.mirabilenet_is_customer",
                 "commercial_partner_id.mirabilenet_region_id")
    def _compute_mirabilenet_scope(self):
        for partner in self:
            owner = partner.commercial_partner_id or partner
            partner.mirabilenet_restricted = owner.mirabilenet_is_customer
            partner.mirabilenet_scope_region_id = (
                owner.mirabilenet_region_id if owner.mirabilenet_is_customer else False)

    @api.constrains("mirabilenet_is_customer", "mirabilenet_region_id",
                    "mirabilenet_zone_id", "mirabilenet_branch_id")
    def _check_mirabilenet_region(self):
        for partner in self:
            region = partner.mirabilenet_region_id
            if partner.mirabilenet_is_customer and not region:
                raise ValidationError(_("Todo cliente pertenece a una región."))
            if partner.mirabilenet_zone_id and partner.mirabilenet_zone_id.region_id != region:
                raise ValidationError(_("La zona no pertenece a la región del cliente."))
            if (partner.mirabilenet_branch_id
                    and partner.mirabilenet_branch_id.region_id != region):
                raise ValidationError(_("La sucursal no pertenece a la región del cliente."))

    # ------------------------------------------------------------------
    def _mirabilenet_require_manager(self, contacts_only=False):
        if self.env.su or self.env.user.has_group(CUSTOMER_MANAGER):
            return
        if contacts_only and self.env.user.has_group(CONTACT_MANAGER):
            return
        raise AccessError(_("Su rol no puede crear ni modificar clientes."))

    def _mirabilenet_state_allowed(self):
        # Solo el código del sistema: el contexto lo envía el cliente y no prueba nada.
        return self.env.su

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            parent = self.browse(vals.get("parent_id")).sudo()
            if not vals.get("mirabilenet_is_customer") and not parent.mirabilenet_restricted:
                continue
            self._mirabilenet_require_manager(
                contacts_only=not vals.get("mirabilenet_is_customer"))
            if not vals.get("mirabilenet_is_customer"):
                continue
            if (vals.get("mirabilenet_state", "prospecto") != "prospecto"
                    and not self._mirabilenet_state_allowed()):
                raise UserError(_("Un cliente nuevo empieza como prospecto."))
            if not vals.get("mirabilenet_code"):
                vals["mirabilenet_code"] = self.env["ir.sequence"].sudo().next_by_code(
                    "mirabilenet.customer")
        return super().create(vals_list)

    def write(self, vals):
        business = [name for name in vals if not name.startswith(TECHNICAL_PREFIXES)]
        if business and (vals.get("mirabilenet_is_customer")
                         or any(self.sudo().mapped("mirabilenet_restricted"))):
            touches_customer = bool(
                vals.get("mirabilenet_is_customer") or "parent_id" in vals
                or any(self.sudo().mapped("mirabilenet_is_customer")))
            self._mirabilenet_require_manager(contacts_only=not touches_customer)
        if "mirabilenet_state" in vals and not self._mirabilenet_state_allowed():
            raise UserError(_("El estado comercial cambia con los botones del cliente."))
        result = super().write(vals)
        if vals.get("mirabilenet_is_customer"):
            for partner in self.sudo().filtered(lambda p: not p.mirabilenet_code):
                partner.mirabilenet_code = self.env["ir.sequence"].sudo().next_by_code(
                    "mirabilenet.customer")
        return result

    def action_mirabilenet_set_state(self, target=None):
        """Único camino para cambiar el estado comercial."""
        target = target or self.env.context.get("mirabilenet_target")
        labels = dict(STATES)
        if target not in labels:
            raise UserError(_("Estado comercial desconocido."))
        self._mirabilenet_require_manager()
        self.check_access("write")
        for partner in self:
            if not partner.mirabilenet_is_customer:
                raise UserError(_("%s no es un cliente.", partner.display_name))
            if target not in TRANSITIONS[partner.mirabilenet_state]:
                raise UserError(_(
                    "%(name)s no puede pasar de «%(old)s» a «%(new)s».",
                    name=partner.display_name, old=labels[partner.mirabilenet_state],
                    new=labels[target]))
        # Permisos y región ya se comprobaron arriba, como el usuario.
        self.sudo().write({"mirabilenet_state": target})
        return True
