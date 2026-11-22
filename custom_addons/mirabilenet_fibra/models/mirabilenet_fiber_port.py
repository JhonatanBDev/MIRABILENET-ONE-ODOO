from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

FIBER_MANAGER = "mirabilenet_fibra.group_mirabilenet_fiber_manager"
PORT_STATES = [
    ("libre", "Libre"),
    ("ocupado", "Ocupado"),
    ("danado", "Dañado"),
    ("reservado", "Reservado"),
]
#: Lo único que el usuario de fibra (no gestor) puede cambiar en un puerto.
USER_FIELDS = {"service_id", "state", "notes", "assigned_date"}


class MirabilenetFiberPort(models.Model):
    """Puerto de una NAP. Se asigna al servicio, no al cliente."""
    _name = "mirabilenet.fiber.port"
    _description = "MIRABILENET: puerto de NAP"
    _inherit = ["mail.thread", "mirabilenet.region.scoped"]
    _order = "nap_id, number"
    _region_path = ("nap_id",)

    name = fields.Char(string="Puerto", compute="_compute_name", store=True)
    nap_id = fields.Many2one("mirabilenet.fiber.nap", string="NAP", required=True,
                             ondelete="cascade", index=True)
    number = fields.Integer(string="Número", required=True)
    state = fields.Selection(PORT_STATES, string="Estado", default="libre", required=True,
                             index=True, tracking=True)
    service_id = fields.Many2one(
        "mirabilenet.service", string="Servicio", ondelete="set null", index=True,
        tracking=True, domain="[('region_id', '=', region_id), ('state', '!=', 'baja')]")
    partner_id = fields.Many2one(related="service_id.partner_id", store=True, index=True,
                                 string="Cliente")
    assigned_date = fields.Date(string="Fecha de asignación", copy=False)
    notes = fields.Text(string="Notas")
    region_id = fields.Many2one(related="nap_id.region_id", store=True, index=True,
                                string="Región")
    company_id = fields.Many2one(related="nap_id.company_id", store=True, index=True,
                                 string="Compañía")
    branch_line = fields.Char(related="nap_id.branch_line", string="Ramal")
    neighborhood = fields.Char(related="nap_id.neighborhood", string="Zona o barrio")
    service_ip = fields.Char(string="IP del cliente", compute="_compute_service_access",
                             store=True, index=True)
    pppoe_username = fields.Char(string="Usuario PPPoE", compute="_compute_service_access",
                                 store=True, index=True)

    @api.depends("service_id.pppoe_ids.fixed_ip", "service_id.pppoe_ids.username")
    def _compute_service_access(self):
        for port in self:
            account = port.service_id.sudo().pppoe_ids[:1]
            port.service_ip = account.fixed_ip or False
            port.pppoe_username = account.username or False

    _nap_number_uniq = models.Constraint(
        "unique(nap_id, number)", "Ese número de puerto ya existe en la NAP.")
    _service_uniq = models.UniqueIndex(
        "(service_id) WHERE service_id IS NOT NULL",
        "Ese servicio ya tiene un puerto asignado. Libérelo primero.")
    _state_service = models.Constraint(
        "CHECK((service_id IS NULL AND state != 'ocupado') "
        "OR (service_id IS NOT NULL AND state != 'libre'))",
        "Un puerto ocupado tiene servicio y uno libre no.")
    _number_positive = models.Constraint("CHECK(number > 0)",
                                         "El número de puerto empieza en 1.")

    @api.depends("nap_id.code", "number")
    def _compute_name(self):
        for port in self:
            port.name = "%s / P%s" % (port.nap_id.code or "", port.number)

    @api.constrains("service_id", "nap_id")
    def _check_service(self):
        for port in self:
            service = port.service_id
            if not service:
                continue
            if service.region_id != port.region_id:
                raise ValidationError(_("El servicio y la NAP deben ser de la misma región."))

    # ------------------------------------------------------------------
    @api.model
    def _prepare_assignment(self, vals, current_state=None):
        """Estado y fecha coherentes con el servicio que se asigna o se quita."""
        if "service_id" in vals:
            if vals["service_id"]:
                service = self.env["mirabilenet.service"].browse(vals["service_id"])
                if service.state == "baja":
                    raise UserError(_("%s está de baja: no se le asigna un puerto.",
                                      service.display_name))
                if current_state == "danado" and vals.get("state", "danado") == "danado":
                    raise UserError(_("El puerto está dañado: no se puede asignar."))
                vals.setdefault("state", "ocupado")
                vals.setdefault("assigned_date", fields.Date.context_today(self))
            else:
                if "state" not in vals and current_state != "danado":
                    vals["state"] = "libre"
                vals.setdefault("assigned_date", False)
        elif vals.get("state") == "libre":
            vals["service_id"] = False
            vals.setdefault("assigned_date", False)
        return vals

    def _check_user_fields(self, vals):
        if self.env.su or self.env.user.has_group(FIBER_MANAGER):
            return
        if set(vals) - USER_FIELDS - {"message_main_attachment_id"}:
            raise AccessError(_("Solo el gestor de fibra cambia los datos del puerto; "
                                "usted puede asignarlo, liberarlo o marcar su estado."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._prepare_assignment(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._check_user_fields(vals)
        if "service_id" in vals or vals.get("state") == "libre":
            if len(self) > 1 and vals.get("service_id"):
                raise UserError(_("Un servicio va en un solo puerto."))
            for port in self:
                super(MirabilenetFiberPort, port).write(
                    port._prepare_assignment(dict(vals), port.state))
            return True
        return super().write(vals)

    def action_release(self):
        self.write({"service_id": False})
        return True

    def action_assign_wizard(self):
        self.ensure_one()
        if self.state not in ("libre", "reservado"):
            raise UserError(_("Solo se asigna un puerto libre o reservado."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Asignar cliente a puerto"),
            "res_model": "mirabilenet.fiber.port.assign",
            "view_mode": "form",
            "target": "new",
            "context": {"default_port_id": self.id, "default_nap_id": self.nap_id.id},
        }

    def action_open_map(self):
        self.ensure_one()
        return self.nap_id.action_open_map()
