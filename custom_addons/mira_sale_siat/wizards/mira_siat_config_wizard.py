from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..siat import errors as siat_errors

MANAGER = "mira_sale_siat.group_mira_siat_manager"

STEPS = [
    ("company", "Empresa"),
    ("connection", "Conexión"),
    ("branches", "Sucursales y puntos de venta"),
    ("token", "Token delegado"),
    ("sync", "Códigos y catálogos"),
    ("defaults", "Parámetros de emisión"),
    ("done", "Listo"),
]

# Qué se envía al SIN al avanzar en cada paso.
_NOTICES = {
    "company": "Este paso no envía nada al SIN.",
    "connection": "Este paso no envía nada al SIN.",
    "branches": "Este paso solo guarda datos en Odoo. Las sucursales deben existir ya "
                "en la Oficina Virtual del SIN.",
    "token": "Al continuar se pide un CUIS al SIN con este token, para comprobar que funciona.",
    "sync": "Al continuar se registran ante el SIN los puntos de venta nuevos, se piden "
            "CUIS y CUFD y se descargan los catálogos.",
    "defaults": "Este paso no envía nada al SIN.",
    "done": "",
}


class MiraSiatConfigWizard(models.TransientModel):
    """Asistente de configuración: lleva de la mano hasta poder emitir."""
    _name = "mira.siat.config.wizard"
    _description = "Mira_Sale SIAT: asistente de configuración"

    company_id = fields.Many2one("res.company", required=True, readonly=True,
                                 default=lambda self: self.env.company)
    step = fields.Selection(STEPS, default="company", required=True)
    progress = fields.Char(compute="_compute_progress")
    notice = fields.Char(compute="_compute_progress")
    is_production = fields.Boolean(compute="_compute_progress")
    result_message = fields.Text(readonly=True)

    # Empresa
    nit = fields.Char(related="company_id.vat", readonly=False, string="NIT")
    nit_ok = fields.Boolean(compute="_compute_nit_ok")
    # Conexión
    environment = fields.Selection(related="company_id.mira_siat_environment", readonly=False)
    gateway_mode = fields.Selection(related="company_id.mira_siat_gateway_mode", readonly=False)
    modality = fields.Selection(related="company_id.mira_siat_modality", readonly=False)
    system_code = fields.Char(related="company_id.mira_siat_system_code", readonly=False)
    associated = fields.Boolean(
        string="El contribuyente ya está asociado al sistema en la Oficina Virtual")
    # Sucursales
    branch_ids = fields.One2many("mira.siat.config.wizard.branch", "wizard_id")
    # Token
    token = fields.Char(string="Token delegado")
    token_expires_at = fields.Datetime(string="Vence el")
    token_state = fields.Selection(related="company_id.mira_siat_token_state")
    # Parámetros
    currency_item_id = fields.Many2one(
        related="company_id.mira_siat_currency_item_id", readonly=False)
    default_payment_method_id = fields.Many2one(
        related="company_id.mira_siat_default_payment_method_id", readonly=False)
    credit_payment_method_id = fields.Many2one(
        related="company_id.mira_siat_credit_payment_method_id", readonly=False)
    default_unit_id = fields.Many2one(
        related="company_id.mira_siat_default_unit_id", readonly=False)
    default_sector = fields.Selection(
        related="company_id.mira_siat_default_sector", readonly=False)
    activity_ids = fields.Many2many(
        related="company_id.mira_siat_activity_ids", readonly=False)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        company = self.env.company
        values["associated"] = company.mira_siat_association_status == "associated"
        branches = self.env["mira.siat.branch"].search([("company_id", "=", company.id)])
        lines = [(0, 0, {
            "branch_id": branch.id, "code": branch.code, "name": branch.name,
            "address": branch.address, "municipality": branch.municipality,
            "phone": branch.phone, "pos_count": max(len(branch.pos_ids), 1),
        }) for branch in branches]
        values["branch_ids"] = lines or [(0, 0, {
            "code": 0, "name": _("CASA MATRIZ"), "pos_count": 1,
            "address": company.street or "", "municipality": company.city or "",
            "phone": company.phone or "",
        })]
        return values

    def _steps(self):
        """El simulador no usa token: ese paso se omite."""
        self.ensure_one()
        return [key for key, _label in STEPS
                if not (key == "token" and self.gateway_mode == "fake")]

    @api.depends("step", "gateway_mode", "environment")
    def _compute_progress(self):
        labels = dict(STEPS)
        for wizard in self:
            steps = wizard._steps()
            index = steps.index(wizard.step) + 1 if wizard.step in steps else 1
            wizard.progress = _("Paso %(i)s de %(n)s: %(label)s", i=index, n=len(steps),
                                label=labels[wizard.step])
            wizard.is_production = (
                wizard.environment == "1" and wizard.gateway_mode == "real")
            notice = _NOTICES[wizard.step]
            if wizard.gateway_mode == "fake" and wizard.step in ("token", "sync"):
                notice = "Modo simulador: nada de este paso llega al SIN."
            elif wizard.is_production and wizard.step in ("token", "sync"):
                notice = "PRODUCCIÓN: lo que haga en este paso tiene efecto fiscal real. " + notice
            wizard.notice = notice

    @api.depends("nit")
    def _compute_nit_ok(self):
        for wizard in self:
            wizard.nit_ok = bool((wizard.nit or "").strip().isdigit())

    # ---- navegación -------------------------------------------------------
    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "name": _("Asistente de configuración SIAT"),
        }

    def action_next(self):
        """Valida y aplica el paso en el servidor; no se puede saltar pasos."""
        self.ensure_one()
        service = self.env["mira.siat.service"]
        service._require_group(MANAGER, "config.wizard")
        try:
            getattr(self, "_apply_%s" % self.step)()
        except siat_errors.SiatError as exc:
            raise service._user_error(exc)
        steps = self._steps()
        position = steps.index(self.step)
        if position < len(steps) - 1:
            self.step = steps[position + 1]
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        steps = self._steps()
        position = steps.index(self.step) if self.step in steps else 0
        if position > 0:
            self.step = steps[position - 1]
        return self._reopen()

    def action_finish(self):
        return {"type": "ir.actions.act_window_close"}

    # ---- pasos ------------------------------------------------------------
    def _apply_company(self):
        if not self.nit_ok:
            raise UserError(_("Escriba el NIT de la empresa, solo con dígitos."))
        self.company_id.mira_siat_enabled = True

    def _apply_connection(self):
        company = self.company_id
        if self.gateway_mode == "fake" and self.environment == "1":
            raise UserError(_("El simulador no puede usarse en PRODUCCIÓN."))
        if self.modality == "1":
            raise UserError(_(
                "Esta versión solo emite en modalidad Computarizada en Línea."))
        if self.gateway_mode == "real":
            if not self.system_code:
                raise UserError(_("Escriba el código de sistema asignado por el SIN."))
            if not self.associated:
                raise UserError(_(
                    "Antes de continuar, asocie el contribuyente al sistema en la "
                    "Oficina Virtual del SIN y marque la casilla."))
        company.mira_siat_association_status = (
            "associated" if (self.associated or self.gateway_mode == "fake") else "pending")

    def _apply_branches(self):
        lines = self.branch_ids
        if not lines:
            raise UserError(_("Agregue al menos una sucursal."))
        codes = lines.mapped("code")
        if len(set(codes)) != len(codes):
            raise UserError(_("Hay números de sucursal repetidos."))
        if 0 not in codes:
            raise UserError(_("La sucursal 0 (casa matriz) es obligatoria."))
        Branch = self.env["mira.siat.branch"]
        Pos = self.env["mira.siat.pos"]
        for line in lines:
            if line.code < 0 or line.pos_count < 1:
                raise UserError(_("Cada sucursal necesita al menos un punto de venta."))
            if not (line.name and line.address and line.municipality):
                raise UserError(_("Complete nombre, dirección y municipio de cada sucursal."))
            vals = {"code": line.code, "name": line.name, "address": line.address,
                    "municipality": line.municipality, "phone": line.phone}
            if not line.branch_id:
                # La pantalla puede no devolver la sucursal ya creada: se busca por número.
                line.branch_id = Branch.search([("company_id", "=", self.company_id.id),
                                                ("code", "=", line.code)], limit=1)
            if line.branch_id:
                line.branch_id.write(vals)
            else:
                line.branch_id = Branch.create(dict(vals, company_id=self.company_id.id))
            branch = line.branch_id
            if len(branch.pos_ids) > line.pos_count:
                raise UserError(_(
                    "La sucursal %s ya tiene más puntos de venta que los indicados. "
                    "Los puntos de venta existentes no se eliminan desde el asistente.",
                    branch.name))
            if not branch.pos_ids.filtered(lambda p: p.code == 0):
                Pos.create({"branch_id": branch.id, "code": 0,
                            "name": _("%s - Punto 0", branch.name)})
            for number in range(len(branch.pos_ids) + 1, line.pos_count + 1):
                Pos.create({"branch_id": branch.id, "register_new": True,
                            "name": _("%(branch)s - Caja %(n)s", branch=branch.name, n=number)})
        company = self.company_id
        if not company._mira_siat_default_pos():
            main = Pos.search([("company_id", "=", company.id), ("code", "=", 0)],
                              order="branch_id", limit=1)
            main.is_default = True

    def _main_pos(self):
        pos = self.env["mira.siat.pos"].search(
            [("company_id", "=", self.company_id.id), ("code", "=", 0)],
            order="branch_id", limit=1)
        if not pos:
            raise UserError(_("Primero configure las sucursales."))
        return pos

    def _apply_token(self):
        company = self.company_id
        if self.token:
            if not self.token_expires_at:
                raise UserError(_("Indique la fecha de vencimiento del token."))
            company._mira_siat_set_token(self.token, self.token_expires_at)
            self.token = False
        elif company.mira_siat_token_state != "valid":
            raise UserError(_("Pegue el token delegado vigente de la empresa."))
        # Prueba real: si el token no sirve, el SIN lo rechaza aquí.
        self._main_pos()._renew_cuis()

    def _apply_sync(self):
        company = self.company_id
        points = self.env["mira.siat.pos"].search(
            [("company_id", "=", company.id)], order="code desc")
        tipo = self.env["mira.siat.catalog.item"]
        main = self._main_pos()
        main._get_cuis()
        self.env["mira.siat.catalog"]._sync(main)
        pending = points.filtered(lambda p: p.code < 0)
        if pending:
            tipo = tipo.search([("company_id", "=", company.id),
                                ("catalog_type", "=", "tipo_punto_venta")])
            for pos in pending:
                if not pos.pos_type_id:
                    if len(tipo) != 1:
                        raise UserError(_(
                            "Indique el tipo del punto de venta «%s» (Configuración SIAT > "
                            "Puntos de venta) y vuelva a este paso.", pos.name))
                    pos.pos_type_id = tipo
                pos._register_with_sin()
        for pos in points:
            pos._get_cuis()
            pos._get_cufd()
        self.result_message = _(
            "%(n)s punto(s) de venta con CUIS y CUFD vigentes. Catálogos sincronizados.",
            n=len(points))

    def _apply_defaults(self):
        company = self.company_id
        if not company.mira_siat_currency_item_id:
            raise UserError(_("Elija el código de moneda SIN de la moneda de la empresa."))
        if not company.mira_siat_default_payment_method_id:
            raise UserError(_("Elija el método de pago por defecto."))
        company.mira_siat_currency_item_id.sudo().currency_id = company.currency_id

    def _apply_done(self):
        return True


class MiraSiatConfigWizardBranch(models.TransientModel):
    _name = "mira.siat.config.wizard.branch"
    _description = "Mira_Sale SIAT: sucursal del asistente"

    wizard_id = fields.Many2one("mira.siat.config.wizard", required=True, ondelete="cascade")
    branch_id = fields.Many2one("mira.siat.branch", readonly=True)
    code = fields.Integer(string="N.º de sucursal", required=True)
    name = fields.Char(string="Nombre")
    address = fields.Char(string="Dirección")
    municipality = fields.Char(string="Municipio", size=25)
    phone = fields.Char(string="Teléfono")
    pos_count = fields.Integer(string="Puntos de venta", default=1, required=True)
    existing_count = fields.Integer(string="Ya creados", compute="_compute_existing_count")

    @api.depends("branch_id")
    def _compute_existing_count(self):
        for line in self:
            line.existing_count = len(line.branch_id.pos_ids)
