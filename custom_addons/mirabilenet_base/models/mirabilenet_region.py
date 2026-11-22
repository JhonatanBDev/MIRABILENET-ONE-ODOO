from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

DAY_FIELDS = ("dia_emision", "dia_vencimiento", "dia_emision_prepago")


class MirabilenetRegion(models.Model):
    """Región operativa. Todo registro del negocio cuelga de una."""
    _name = "mirabilenet.region"
    _description = "MIRABILENET: región"
    _inherit = ["mail.thread"]
    _order = "name"

    company_id = fields.Many2one("res.company", string="Empresa", required=True,
                                 default=lambda self: self.env.company)
    code = fields.Char(string="Código", required=True, size=20, tracking=True)
    name = fields.Char(string="Nombre", required=True, tracking=True)
    wg_region_id = fields.Integer(
        string="Id de región para direccionamiento", required=True,
        help="0 a 63. Define la red de gestión y el bloque de cámaras.")
    active = fields.Boolean(string="Activa", default=True, tracking=True)
    currency_id = fields.Many2one(
        "res.currency", string="Moneda", required=True,
        default=lambda self: self.env.ref("base.BOB", raise_if_not_found=False)
        or self.env.company.currency_id)

    # Calendario de cobro: es por región, no por cliente.
    dia_emision = fields.Integer(
        string="Día de emisión (pospago, sin uso)", default=1, tracking=True,
        help="Ya no se usa: cada servicio pospago se cobra el día de su alta. Se conserva "
             "para la migración del sistema anterior.")
    dia_vencimiento = fields.Integer(
        string="Día de vencimiento (prepago)", default=10, tracking=True,
        help="Día del mes en que vence el cobro prepago. El pospago vence el mismo día "
             "en que se emite.")
    dia_emision_prepago = fields.Integer(
        string="Día de emisión (prepago)", default=1, tracking=True,
        help="Día del mes en que se genera y notifica el cobro prepago.")
    prorrateo_prepago_activacion = fields.Boolean(
        string="Prorratear prepago al activar", default=True, tracking=True,
        help="Cobra desde el día siguiente al alta hasta el fin de ese mes.")
    prorrateo_prepago_desde = fields.Date(
        string="Aplicar prorrateo desde", default=fields.Date.context_today, tracking=True,
        help="Evita generar cargos iniciales retroactivos a servicios que ya existían.")
    dias_gracia = fields.Integer(
        string="Días de gracia", default=3, tracking=True,
        help="Días después del vencimiento antes del corte automático. Con 0, el corte "
             "llega al día siguiente de vencer.")
    hora_corte = fields.Float(string="Hora de corte", default=9.0, tracking=True)
    suspension_automatica = fields.Boolean(string="Suspensión automática", tracking=True)
    reactivacion_automatica = fields.Boolean(string="Reactivación automática", default=True,
                                             tracking=True)

    objetivo_mrr = fields.Monetary(string="Objetivo de ingreso mensual",
                                   currency_field="currency_id")
    precio_referencia = fields.Monetary(string="Precio de referencia por cliente",
                                        currency_field="currency_id")

    bloque_gestion = fields.Char(string="Red de gestión", compute="_compute_bloques")
    bloque_camaras = fields.Char(string="Bloque de cámaras", compute="_compute_bloques")

    branch_ids = fields.One2many("mirabilenet.branch", "region_id", string="Sucursales")
    zone_ids = fields.One2many("mirabilenet.zone", "region_id", string="Zonas")

    _code_uniq = models.Constraint("unique(code)", "Ya existe una región con ese código.")
    _wg_uniq = models.Constraint(
        "unique(wg_region_id)", "Ese id de direccionamiento ya lo usa otra región.")
    _wg_range = models.Constraint(
        "CHECK(wg_region_id >= 0 AND wg_region_id <= 63)",
        "El id de direccionamiento debe estar entre 0 y 63.")

    @api.model
    def _mirabilenet_coverage_localities(self):
        """Localidades con cobertura publicadas en el sitio: (región, nombre, estado, detalle).
        Aquí no hay ninguna; las aporta el módulo del sitio web."""
        return []

    @api.depends("wg_region_id")
    def _compute_bloques(self):
        for region in self:
            region.bloque_gestion = "10.250.%d.0/24" % (region.wg_region_id * 10)
            region.bloque_camaras = "10.%d.0.0/16" % (64 + region.wg_region_id)

    @api.constrains(*DAY_FIELDS, "dias_gracia", "hora_corte")
    def _check_calendar(self):
        for region in self:
            if any(not 1 <= region[name] <= 31 for name in DAY_FIELDS):
                raise ValidationError(_("Los días de emisión y de vencimiento van de 1 a 31."))
            if region.dias_gracia < 0:
                raise ValidationError(_("Los días de gracia no pueden ser negativos."))
            if not 0 <= region.hora_corte < 24:
                raise ValidationError(_("La hora de corte va de 00:00 a 23:59."))

    def unlink(self):
        raise UserError(_("Una región no se elimina: se desactiva."))
