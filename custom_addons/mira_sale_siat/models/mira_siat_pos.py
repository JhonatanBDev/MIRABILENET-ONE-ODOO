import datetime
import uuid

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from ..siat import errors as siat_errors
from ..siat.gateway import SiatContext

MANAGER = "mira_sale_siat.group_mira_siat_manager"


class MiraSiatPos(models.Model):
    _name = "mira.siat.pos"
    _description = "Mira_Sale SIAT: punto de venta"
    _order = "company_id, branch_id, code"

    name = fields.Char(string="Nombre", required=True)
    branch_id = fields.Many2one(
        "mira.siat.branch", string="Sucursal", required=True, ondelete="restrict")
    company_id = fields.Many2one(
        related="branch_id.company_id", store=True, index=True, string="Empresa")
    code = fields.Integer(
        string="Código SIAT", required=True, default=0, copy=False,
        help="Código de punto de venta ante el SIN. 0 = punto de venta principal de la "
             "sucursal. Un código negativo es provisional: el punto aún no fue "
             "registrado ante el SIN y no puede emitir.")
    pending_registration = fields.Boolean(
        string="Pendiente de registrar ante el SIN", compute="_compute_pending_registration",
        store=True)
    pos_type_id = fields.Many2one(
        "mira.siat.catalog.item", string="Tipo de punto de venta",
        domain="[('catalog_type', '=', 'tipo_punto_venta'), ('company_id', '=', company_id)]")
    is_default = fields.Boolean(string="Punto de venta por defecto")
    active = fields.Boolean(default=True)
    cuis_ids = fields.One2many("mira.siat.cuis", "pos_id", string="CUIS")
    cufd_ids = fields.One2many("mira.siat.cufd", "pos_id", string="CUFD")
    cuis_valid_until = fields.Datetime(
        string="CUIS vigente hasta", compute="_compute_health")
    cufd_valid_until = fields.Datetime(
        string="CUFD vigente hasta", compute="_compute_health")
    last_error_at = fields.Datetime(string="Última falla de comunicación", readonly=True)
    connectivity_state = fields.Selection(
        [("online", "En línea"), ("degraded", "Degradado"), ("contingency", "Contingencia")],
        string="Estado SIAT", compute="_compute_health")

    _code_branch_uniq = models.Constraint(
        "unique(branch_id, code)",
        "Ya existe un punto de venta con ese código en la sucursal.")

    @api.depends("code")
    def _compute_pending_registration(self):
        for pos in self:
            pos.pending_registration = pos.code < 0

    @api.model_create_multi
    def create(self, vals_list):
        """Un punto nuevo que todavía no existe en el SIN recibe un código
        provisional negativo, que nunca se envía al SIN."""
        for vals in vals_list:
            if vals.pop("register_new", False) or self.env.context.get("mira_siat_new_pos"):
                self.env.cr.execute("SELECT pg_advisory_xact_lock(hashtext('mira_siat_pos'))")
                self.env.cr.execute("SELECT COALESCE(MIN(code), 0) FROM mira_siat_pos")
                lowest = min(self.env.cr.fetchone()[0], 0)
                taken = [v.get("code", 0) for v in vals_list if isinstance(v.get("code"), int)]
                vals["code"] = min([lowest] + taken) - 1
        return super().create(vals_list)

    @api.constrains("is_default", "company_id")
    def _check_single_default(self):
        for pos in self.filtered("is_default"):
            others = self.search_count([
                ("company_id", "=", pos.company_id.id), ("is_default", "=", True),
                ("id", "!=", pos.id)])
            if others:
                raise ValidationError(_(
                    "La empresa ya tiene otro punto de venta por defecto."))

    @api.depends("cuis_ids.valid_until", "cufd_ids.valid_until", "last_error_at")
    def _compute_health(self):
        now = fields.Datetime.now()
        open_events = self.env["mira.siat.event"].sudo().search([
            ("pos_id", "in", self.ids), ("state", "=", "open"), ("kind", "=", "live"),
        ]).mapped("pos_id")
        for pos in self:
            cuis = pos.cuis_ids.filtered(lambda c: c.active)[:1]
            cufd = pos.cufd_ids.filtered(lambda c: c.active)[:1]
            pos.cuis_valid_until = cuis.valid_until
            pos.cufd_valid_until = cufd.valid_until
            if pos in open_events:
                pos.connectivity_state = "contingency"
            elif pos.last_error_at and pos.last_error_at > now - datetime.timedelta(minutes=15):
                pos.connectivity_state = "degraded"
            else:
                pos.connectivity_state = "online"

    # ---- contexto fiscal --------------------------------------------------
    def _siat_context(self):
        self.ensure_one()
        if self.code < 0:
            raise siat_errors.SiatError(
                siat_errors.TENANT,
                "El punto de venta «%s» todavía no está registrado ante el SIN."
                % self.name)
        company = self.company_id
        return SiatContext(
            nit=(company.vat or "").strip(),
            system_code=company.mira_siat_system_code or "",
            environment=int(company.mira_siat_environment),
            modality=int(company.mira_siat_modality),
            branch_code=self.branch_id.code,
            pos_code=self.code,
        )

    def _mark_comm_error(self):
        self.sudo().write({"last_error_at": fields.Datetime.now()})

    # ---- CUIS -------------------------------------------------------------
    def _get_cuis(self, renew=True):
        """CUIS vigente del punto de venta; lo solicita si no hay uno."""
        self.ensure_one()
        cuis = self.env["mira.siat.cuis"].sudo().search([
            ("pos_id", "=", self.id), ("active", "=", True),
            ("valid_until", ">", fields.Datetime.now()),
        ], limit=1)
        if cuis:
            return cuis
        if not renew:
            raise siat_errors.SiatError(siat_errors.CUIS)
        return self._renew_cuis()

    def _renew_cuis(self):
        self.ensure_one()
        service = self.env["mira.siat.service"]
        self.company_id._mira_siat_check_active()
        correlation = str(uuid.uuid4())
        data = self.company_id._mira_siat_gateway(correlation).request_cuis(
            self._siat_context())
        Cuis = self.env["mira.siat.cuis"].sudo()
        Cuis.search([("pos_id", "=", self.id), ("active", "=", True)]).write(
            {"active": False})
        cuis = Cuis.create({
            "pos_id": self.id,
            "code_encrypted": service._vault().encrypt(data["code"]),
            "valid_until": service._to_utc_naive(data["valid_until"]),
        })
        service._audit("cuis.renew", self, after={"valid_until": str(cuis.valid_until)},
                       correlation_id=correlation)
        return cuis

    # ---- CUFD -------------------------------------------------------------
    def _get_cufd(self, renew=True):
        """CUFD vigente; lo renueva si venció (solo antes de asignar documento)."""
        self.ensure_one()
        limit = fields.Datetime.now() + datetime.timedelta(minutes=1)
        cufd = self.env["mira.siat.cufd"].sudo().search([
            ("pos_id", "=", self.id), ("active", "=", True), ("valid_until", ">", limit),
        ], limit=1)
        if cufd:
            return cufd
        if not renew:
            raise siat_errors.SiatError(siat_errors.CUFD)
        return self._renew_cufd()

    def _last_cufd(self):
        """Último CUFD obtenido, aunque haya vencido (lo usa la contingencia)."""
        self.ensure_one()
        return self.env["mira.siat.cufd"].sudo().with_context(active_test=False).search(
            [("pos_id", "=", self.id)], order="valid_from desc, id desc", limit=1)

    def _cufd_at(self, when):
        """CUFD que estaba vigente en una fecha pasada."""
        self.ensure_one()
        return self.env["mira.siat.cufd"].sudo().with_context(active_test=False).search([
            ("pos_id", "=", self.id), ("valid_from", "<=", when), ("valid_until", ">", when),
        ], order="valid_from desc, id desc", limit=1)

    def _renew_cufd(self):
        self.ensure_one()
        service = self.env["mira.siat.service"]
        self.company_id._mira_siat_check_active()
        correlation = str(uuid.uuid4())
        cuis = self._get_cuis()
        data = self.company_id._mira_siat_gateway(correlation).request_cufd(
            self._siat_context(), cuis._code())
        vault = service._vault()
        Cufd = self.env["mira.siat.cufd"].sudo()
        Cufd.search([("pos_id", "=", self.id), ("active", "=", True)]).write(
            {"active": False})
        cufd = Cufd.create({
            "pos_id": self.id,
            "code_encrypted": vault.encrypt(data["code"]),
            "control_code_encrypted": vault.encrypt(data["control_code"]),
            "address": data["address"],
            "valid_from": fields.Datetime.now(),
            "valid_until": service._to_utc_naive(data["valid_until"]),
        })
        service._audit("cufd.renew", self, after={"valid_until": str(cufd.valid_until)},
                       correlation_id=correlation)
        return cufd

    # ---- registro ante el SIN --------------------------------------------
    def _main_pos(self):
        """Punto de venta 0 de la misma sucursal: su CUIS autoriza los registros."""
        self.ensure_one()
        main = self.search([("branch_id", "=", self.branch_id.id), ("code", "=", 0)], limit=1)
        if not main:
            raise siat_errors.SiatError(
                siat_errors.TENANT,
                "La sucursal necesita su punto de venta 0 para registrar otros.")
        return main

    def _register_with_sin(self):
        """Registra el punto ante el SIN y guarda el código que este asigna."""
        self.ensure_one()
        if self.code >= 0:
            return self.code
        if not self.pos_type_id:
            raise siat_errors.SiatError(
                siat_errors.TENANT, "Indique el tipo de punto de venta antes de registrarlo.")
        service = self.env["mira.siat.service"]
        self.company_id._mira_siat_check_active()
        main = self._main_pos()
        correlation = str(uuid.uuid4())
        code = self.company_id._mira_siat_gateway(correlation).register_pos(
            main._siat_context(), main._get_cuis()._code(), int(self.pos_type_id.code),
            self.name, self.name)
        self.sudo().write({"code": code})
        service._audit("pos.register", self, after={"code": code},
                       correlation_id=correlation)
        return code

    def _close(self):
        self.ensure_one()
        service = self.env["mira.siat.service"]
        if self.code <= 0:
            raise siat_errors.SiatError(
                siat_errors.TENANT, "Solo se cierra un punto de venta registrado (código > 0).")
        main = self._main_pos()
        correlation = str(uuid.uuid4())
        result = self.company_id._mira_siat_gateway(correlation).close_pos(
            main._siat_context(), main._get_cuis()._code(), self.code)
        if not result.ok:
            raise siat_errors.SiatError(
                siat_errors.REJECTED, "El SIN no cerró el punto de venta.", result.messages)
        self.sudo().write({"active": False, "is_default": False})
        service._audit("pos.close", self, correlation_id=correlation)

    def _verify_nit(self, nit):
        """Consulta al SIN si un NIT está activo. Devuelve un SiatResult."""
        self.ensure_one()
        self.company_id._mira_siat_check_active()
        return self.company_id._mira_siat_gateway().verify_nit(
            self._siat_context(), self._get_cuis()._code(), nit)

    # ---- acciones ---------------------------------------------------------
    def _run_admin(self, action, method):
        service = self.env["mira.siat.service"]
        service._require_group(MANAGER, action)
        try:
            for pos in self:
                method(pos)
        except siat_errors.SiatError as exc:
            if isinstance(exc, siat_errors.SiatCommunicationError):
                self._mark_comm_error()
            text = " ".join(
                [exc.message] + [str(d) for d in exc.details or []]).upper()
            if "SUCURSAL" in text:
                exc.details = list(exc.details or []) + [_(
                    "Pista: la sucursal debe estar registrada primero en la Oficina "
                    "Virtual del SIN, con el mismo número.")]
            raise service._user_error(exc)
        return True

    def action_register(self):
        return self._run_admin("pos.register", lambda pos: pos._register_with_sin())

    def action_close_pos(self):
        return self._run_admin("pos.close", lambda pos: pos._close())

    def action_refresh_cuis(self):
        return self._run_admin("cuis.refresh", lambda pos: pos._renew_cuis())

    def action_refresh_cufd(self):
        return self._run_admin("cufd.refresh", lambda pos: pos._renew_cufd())

    def action_sync_catalogs(self):
        return self._run_admin(
            "catalogs.sync", lambda pos: self.env["mira.siat.catalog"]._sync(pos))

    def action_check_health(self):
        self.ensure_one()
        service = self.env["mira.siat.service"]
        try:
            self.company_id._mira_siat_check_active()
            ok = self.company_id._mira_siat_gateway().check_communication(
                self._siat_context())
        except siat_errors.SiatError as exc:
            self._mark_comm_error()
            raise service._user_error(exc)
        if not ok:
            raise UserError(_("El SIN respondió, pero reporta el servicio no disponible."))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("SIAT"), "type": "success",
                       "message": _("Comunicación correcta con el SIN.")},
        }
