"""La alerta de objetivo de MRR por región: lo único de los indicadores que no sale de Odoo ni
de mis_builder. Con la capacidad instalada y el precio de referencia, ¿alcanza el objetivo?"""
import math

from odoo import api, fields, models, _

COUNTED_STATES = ("activo", "moroso")


class MirabilenetRegion(models.Model):
    _inherit = "mirabilenet.region"

    mirabilenet_mrr = fields.Monetary(string="MRR actual", compute="_compute_mirabilenet_goal",
                                      help="Mensualidad de los servicios activos y morosos.")
    mirabilenet_capacity = fields.Integer(string="Capacidad instalada",
                                          compute="_compute_mirabilenet_goal")
    mirabilenet_ceiling = fields.Monetary(
        string="Techo de ingreso", compute="_compute_mirabilenet_goal",
        help="Capacidad instalada por precio de referencia.")
    mirabilenet_customers_needed = fields.Integer(string="Clientes necesarios",
                                                  compute="_compute_mirabilenet_goal")
    mirabilenet_goal_state = fields.Selection(
        [("sin_datos", "—"), ("alcanzable", "Alcanzable"), ("no_alcanzable", "No alcanzable")],
        string="Objetivo", compute="_compute_mirabilenet_goal")
    mirabilenet_goal_message = fields.Char(string="Lectura", compute="_compute_mirabilenet_goal")

    @api.depends("objetivo_mrr", "precio_referencia")
    def _compute_mirabilenet_goal(self):
        Service = self.env["mirabilenet.service"].sudo()
        Node = self.env["mirabilenet.node"].sudo()
        for region in self:
            currency = region.currency_id.name or ""
            mrr = sum(Service.search([("region_id", "=", region.id),
                                      ("state", "in", COUNTED_STATES)]).mapped("monthly_price"))
            capacity = sum(Node.search([("region_id", "=", region.id)]).mapped(
                "capacidad_instalada"))
            goal, price = region.objetivo_mrr, region.precio_referencia
            region.mirabilenet_mrr = mrr
            region.mirabilenet_capacity = capacity
            if goal <= 0 or price <= 0:
                # Sin objetivo o sin precio no hay cuenta que hacer: se dice, no se pone 0.
                region.mirabilenet_ceiling = 0
                region.mirabilenet_customers_needed = 0
                region.mirabilenet_goal_state = "sin_datos"
                region.mirabilenet_goal_message = _(
                    "— Falta cargar el objetivo de ingreso mensual o el precio de referencia.")
                continue
            needed = math.ceil(goal / price)
            ceiling = capacity * price
            region.mirabilenet_ceiling = ceiling
            region.mirabilenet_customers_needed = needed
            if ceiling >= goal:
                region.mirabilenet_goal_state = "alcanzable"
                region.mirabilenet_goal_message = _(
                    "Alcanzable con la capacidad instalada: hacen falta %(n)s clientes a "
                    "%(p).2f %(c)s.", n=needed, p=price, c=currency)
            else:
                arpu = ("%.2f %s" % (goal / capacity, currency)) if capacity else _(
                    "— (sin capacidad instalada)")
                region.mirabilenet_goal_state = "no_alcanzable"
                region.mirabilenet_goal_message = _(
                    "No alcanzable: con %(cap)s conexiones a %(p).2f %(c)s el techo es "
                    "%(t).2f %(c)s. Hacen falta %(n)s clientes, o un ingreso medio de %(a)s con "
                    "la capacidad actual.", cap=capacity, p=price, c=currency, t=ceiling,
                    n=needed, a=arpu)
