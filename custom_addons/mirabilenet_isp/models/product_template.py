from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

PLAN_MANAGER = "mirabilenet_isp.group_mirabilenet_plan_manager"


class ProductTemplate(models.Model):
    """El plan es un producto de tipo servicio con sus datos de velocidad."""
    _name = "product.template"
    _inherit = ["product.template", "mirabilenet.region.scoped"]
    _region_path = ("mirabilenet_region_id", "mirabilenet_is_plan")

    mirabilenet_is_plan = fields.Boolean(string="Es un plan de internet", index=True)
    mirabilenet_plan_code = fields.Char(string="Código del plan", copy=False, index=True)
    mirabilenet_region_id = fields.Many2one(
        "mirabilenet.region", string="Región", ondelete="restrict", index=True,
        help="Vacío = el plan vale en todas las regiones.")
    mirabilenet_down_mbps = fields.Integer(string="Bajada (Mbps)")
    mirabilenet_up_mbps = fields.Integer(string="Subida (Mbps)")
    mirabilenet_includes_tv = fields.Boolean(string="Incluye TV")
    mirabilenet_ppp_profile = fields.Char(
        string="Perfil PPP", help="Nombre del perfil en el router. Vacío = el código del plan.")
    mirabilenet_reduced_profile = fields.Char(
        string="Perfil de corte parcial", help="Perfil de velocidad reducida.")
    mirabilenet_publish_web = fields.Boolean(
        string="Publicar en la web", copy=False,
        help="Activo y publicado son decisiones distintas. Un plan sin precio no se publica "
             "aunque esté marcado.")
    mirabilenet_published = fields.Boolean(
        string="Publicado", compute="_compute_mirabilenet_published",
        search="_search_mirabilenet_published")
    mirabilenet_profile_name = fields.Char(
        string="Perfil efectivo", compute="_compute_mirabilenet_profile_name")

    _mirabilenet_plan_code_uniq = models.Constraint(
        "unique(mirabilenet_plan_code)", "Ya existe un plan con ese código.")

    @api.depends("active", "mirabilenet_is_plan", "mirabilenet_publish_web", "list_price")
    def _compute_mirabilenet_published(self):
        for plan in self:
            plan.mirabilenet_published = bool(
                plan.mirabilenet_is_plan and plan.active and plan.mirabilenet_publish_web
                and plan.list_price > 0)

    def _search_mirabilenet_published(self, operator, value):
        truthy = any(value) if isinstance(value, (list, tuple, set)) else bool(value)
        positive = truthy if operator in ("=", "in") else not truthy
        published = [("mirabilenet_is_plan", "=", True), ("active", "=", True),
                     ("mirabilenet_publish_web", "=", True), ("list_price", ">", 0)]
        if positive:
            return published
        ids = self.with_context(active_test=False).search(published).ids
        return [("id", "not in", ids)]

    @api.depends("mirabilenet_ppp_profile", "mirabilenet_plan_code")
    def _compute_mirabilenet_profile_name(self):
        for plan in self:
            plan.mirabilenet_profile_name = (
                plan.mirabilenet_ppp_profile or plan.mirabilenet_plan_code)

    @api.constrains("mirabilenet_is_plan", "mirabilenet_plan_code", "mirabilenet_down_mbps",
                    "mirabilenet_up_mbps", "list_price")
    def _check_mirabilenet_plan(self):
        for plan in self.filtered("mirabilenet_is_plan"):
            if not plan.mirabilenet_plan_code:
                raise ValidationError(_("El plan necesita un código."))
            if plan.mirabilenet_down_mbps <= 0 or plan.mirabilenet_up_mbps <= 0:
                raise ValidationError(_("Indique la velocidad de bajada y de subida del plan."))
            if plan.list_price < 0:
                raise ValidationError(_("El precio del plan no puede ser negativo."))

    # ------------------------------------------------------------------
    def _mirabilenet_require_plan_manager(self):
        if not self.env.su and not self.env.user.has_group(PLAN_MANAGER):
            raise AccessError(_("Solo gerencia y administración regional modifican planes."))

    def _mirabilenet_plan_in_use(self):
        """Servicios que usan el plan, incluidos los dados de baja."""
        self.ensure_one()
        return self.env["mirabilenet.service"].sudo().search_count([("plan_id", "=", self.id)])

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get("mirabilenet_is_plan") for vals in vals_list):
            self._mirabilenet_require_plan_manager()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("mirabilenet_is_plan") or any(self.sudo().mapped("mirabilenet_is_plan")):
            self._mirabilenet_require_plan_manager()
        return super().write(vals)

    def unlink(self):
        plans = self.filtered("mirabilenet_is_plan")
        if plans:
            self._mirabilenet_require_plan_manager()
            actor = self.env.user
            is_global = (self.env.su or actor.mirabilenet_is_global
                         or actor._mirabilenet_is_super())
            for plan in plans:
                if not plan.mirabilenet_region_id and not is_global:
                    raise AccessError(_(
                        "Este plan vale para todas las regiones: solo lo elimina un usuario "
                        "con alcance global."))
                used = plan._mirabilenet_plan_in_use()
                if used:
                    raise UserError(_(
                        "No se puede eliminar: lo usan %s servicios (incluidos los dados de "
                        "baja). Para retirarlo, desactívelo y quite «Publicar en la web».",
                        used))
                self.env["mirabilenet.audit.log"]._log(
                    "eliminar",
                    "Plan eliminado: %s %s" % (plan.mirabilenet_plan_code, plan.name),
                    record=plan, region=plan.mirabilenet_region_id,
                    payload={"precio": str(plan.list_price),
                             "bajada_mbps": plan.mirabilenet_down_mbps})
        return super().unlink()
