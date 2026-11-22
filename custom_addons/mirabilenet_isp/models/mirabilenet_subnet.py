from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from ..isp import addressing

KINDS = [
    ("camaras", "Red de cámaras"),
    ("lan_cliente", "LAN de cliente"),
    ("gestion", "Gestión WireGuard"),
]


class MirabilenetSubnet(models.Model):
    """Subred /24 de un sitio: 10.<64+región>.<sitio>.0/24. La asigna el sistema."""
    _name = "mirabilenet.subnet"
    _description = "MIRABILENET: subred"
    _inherit = ["mirabilenet.region.scoped"]
    _order = "region_id, site_id"
    _rec_name = "cidr"

    region_id = fields.Many2one("mirabilenet.region", string="Región", required=True,
                                ondelete="restrict", index=True)
    site_id = fields.Integer(string="Id de sitio", readonly=True)
    cidr = fields.Char(string="Subred", readonly=True, index=True)
    kind = fields.Selection(KINDS, string="Tipo", required=True, default="camaras")
    state = fields.Selection(
        [("reservada", "Reservada"), ("activa", "Activa"), ("cuarentena", "En cuarentena")],
        string="Estado", default="reservada", required=True, index=True)
    partner_id = fields.Many2one("res.partner", string="Cliente", ondelete="set null",
                                 domain="[('mirabilenet_is_customer', '=', True)]")
    description = fields.Char(string="Descripción")
    legacy_network = fields.Char(
        string="Red real heredada",
        help="Solo si el sitio conserva su red original y se traduce con netmap.")
    released_at = fields.Datetime(string="Liberada el", readonly=True)
    gateway = fields.Char(string="Puerta de enlace", compute="_compute_gateway")
    netmap_rules = fields.Text(string="Reglas netmap", compute="_compute_gateway")

    _cidr_uniq = models.Constraint("unique(cidr)", "Esa subred ya existe.")
    _site_uniq = models.Constraint(
        "unique(region_id, site_id, kind)", "Ese sitio ya tiene una subred de ese tipo.")

    @api.depends("cidr", "legacy_network", "site_id", "region_id.name")
    def _compute_gateway(self):
        for subnet in self:
            subnet.gateway = addressing.gateway_of(subnet.cidr) if subnet.cidr else False
            subnet.netmap_rules = addressing.netmap_rules(
                subnet.site_id, subnet.region_id.name, subnet.legacy_network, subnet.cidr,
            ) if subnet.legacy_network and subnet.cidr else False

    @api.constrains("legacy_network")
    def _check_legacy_network(self):
        for subnet in self.filtered("legacy_network"):
            try:
                addressing.parse_networks(subnet.legacy_network)
            except addressing.AddressingError as exc:
                raise ValidationError(str(exc))

    @api.model_create_multi
    def create(self, vals_list):
        """La red no se elige: se reserva la siguiente libre de la región."""
        Region = self.env["mirabilenet.region"]
        supernet = self.env["ir.config_parameter"].sudo().get_param(
            "mirabilenet.camera_supernet", addressing.DEFAULT_SUPERNET)
        taken = {}
        for vals in vals_list:
            region = Region.browse(vals.get("region_id"))
            if not region.exists():
                raise UserError(_("Indique la región de la subred."))
            kind = vals.get("kind") or "camaras"
            # Bloqueo de la región: dos operadores nunca reciben la misma red.
            self.env.cr.execute(
                "SELECT id FROM mirabilenet_region WHERE id = %s FOR UPDATE", [region.id])
            self.flush_model()
            self.env.cr.execute(
                "SELECT site_id FROM mirabilenet_subnet WHERE region_id = %s AND kind = %s",
                [region.id, kind])
            used = {row[0] for row in self.env.cr.fetchall()} | taken.setdefault(
                (region.id, kind), set())
            site = addressing.next_free_site(used)
            if site is not None:
                taken[(region.id, kind)].add(site)
            if site is None:
                raise UserError(_(
                    "La región %(region)s agotó sus %(max)s sitios de ese tipo.",
                    region=region.code, max=addressing.SITE_MAX))
            try:
                cidr = addressing.site_cidr(region.wg_region_id, site)
            except addressing.AddressingError as exc:
                raise UserError(str(exc))
            if not addressing.within_supernet(cidr, supernet):
                raise UserError(_("%(cidr)s cae fuera de %(net)s.", cidr=cidr, net=supernet))
            vals.update(site_id=site, cidr=cidr, kind=kind, state="reservada",
                        released_at=False)
        subnets = super().create(vals_list)
        for subnet in subnets:
            self.env["mirabilenet.audit.log"]._log(
                "subred_asignar",
                "Subred %s asignada al sitio %s de %s" % (
                    subnet.cidr, subnet.site_id, subnet.region_id.code),
                record=subnet, region=subnet.region_id,
                payload={"cidr": subnet.cidr, "site_id": subnet.site_id, "kind": subnet.kind})
        return subnets

    def write(self, vals):
        if {"site_id", "cidr", "kind", "region_id"} & set(vals) and not self.env.su:
            raise UserError(_("La red de una subred no se edita: libérela y reserve otra."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise UserError(_("Una subred no se elimina: se libera y pasa a cuarentena."))
        return super().unlink()

    def action_activate(self):
        self.filtered(lambda s: s.state == "reservada").write({"state": "activa"})
        return True

    def action_release(self):
        """Pasa a cuarentena: no se reutiliza durante 30 días."""
        for subnet in self.filtered(lambda s: s.state != "cuarentena"):
            subnet.write({"state": "cuarentena", "released_at": fields.Datetime.now()})
            self.env["mirabilenet.audit.log"]._log(
                "modificar", "Subred %s liberada a cuarentena" % subnet.cidr,
                record=subnet, region=subnet.region_id)
        return True

    @api.model
    def _cron_purge_quarantine(self):
        """Libera definitivamente el id de sitio cuando vence la cuarentena."""
        limit = fields.Datetime.now() - timedelta(days=addressing.QUARANTINE_DAYS)
        expired = self.sudo().search(
            [("state", "=", "cuarentena"), ("released_at", "<", limit)])
        count = len(expired)
        expired.unlink()
        return count
