import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MirabilenetEnrollmentToken(models.Model):
    """Código de incorporación de un solo uso."""
    _name = "mirabilenet.enrollment.token"
    _description = "MIRABILENET: código de enrolamiento"
    _order = "id desc"
    _rec_name = "router_id"

    token = fields.Char(string="Código", required=True, index=True, readonly=True,
                        groups="base.group_system")
    router_id = fields.Many2one("mirabilenet.router", string="Router", required=True,
                                ondelete="cascade", index=True, readonly=True)
    region_id = fields.Many2one(related="router_id.region_id", store=True, index=True)
    state = fields.Selection(
        [("vigente", "Vigente"), ("usado", "Usado"), ("vencido", "Vencido"),
         ("revocado", "Revocado")], string="Estado", default="vigente", required=True,
        readonly=True)
    expires_at = fields.Datetime(string="Expira", required=True, readonly=True)
    used_at = fields.Datetime(string="Usado el", readonly=True)
    used_from_ip = fields.Char(string="IP de uso", readonly=True)
    user_id = fields.Many2one("res.users", string="Generado por", readonly=True)
    api_password_enc = fields.Char(string="Contraseña generada (cifrada)", readonly=True,
                                   groups="base.group_system")

    _token_uniq = models.Constraint("unique(token)", "Código repetido.")

    def _consume(self, ip=None):
        """Un código se consume una sola vez."""
        self.ensure_one()
        if self.state != "vigente":
            raise UserError(_("El código ya no está vigente."))
        if fields.Datetime.now() >= self.expires_at:
            self.state = "vencido"
            raise UserError(_("El código expiró."))
        self.write({"state": "usado", "used_at": fields.Datetime.now(), "used_from_ip": ip})

    @api.model
    def _cron_expire(self):
        expired = self.sudo().search(
            [("state", "=", "vigente"), ("expires_at", "<", fields.Datetime.now())])
        expired.write({"state": "vencido"})
        return len(expired)

    @api.model
    def _complete(self, payload, ip=None):
        """Lo que invoca el router al final del guion. Devuelve (código HTTP, respuesta).

        Se autentica con el código de un solo uso, no con una sesión.
        """
        Log = self.env["mirabilenet.audit.log"]
        payload = payload if isinstance(payload, dict) else {}
        value = str(payload.get("token") or "").strip()
        public_key = str(payload.get("public_key") or "").strip()
        if not value or not public_key:
            return 400, {"detail": "Faltan token o public_key."}
        self.env.cr.execute(
            "SELECT id FROM mirabilenet_enrollment_token WHERE token = %s FOR UPDATE", [value])
        row = self.env.cr.fetchone()
        token = self.sudo().browse(row[0]) if row else self.sudo()
        if not token:
            Log._log("router_enrolar",
                     "Intento de enrolamiento con un código inexistente desde %s" % ip)
            return 403, {"detail": "Token invalido."}
        router = token.router_id
        if token.state != "vigente" or fields.Datetime.now() >= token.expires_at:
            if token.state == "vigente":
                token.state = "vencido"
            Log._log("router_enrolar",
                     "Enrolamiento rechazado: código no vigente, desde %s" % ip,
                     record=router, region=router.region_id)
            return 403, {"detail": "El token ya no esta vigente."}
        token._consume(ip)

        def text(key, limit=255):
            return str(payload.get(key) or "").strip()[:limit]

        vals = {
            "wg_public_key": public_key[:64],
            "identity": text("identity", 80) or router.identity,
            "serial": text("serial", 60),
            "board_name": text("board", 60),
            "api_address_before": text("api_address_before"),
            "api_password_enc": token.api_password_enc,
            "chk_handshake": False,
            "state": "desconectado",
        }
        if text("version", 30):
            vals["routeros_version"] = text("version", 30)
        router.write(vals)
        self.env["mirabilenet.router.config.change"].sudo().create({
            "router_id": router.id,
            "kind": "enrolamiento",
            "summary": "Guion de enrolamiento v1.1 aplicado",
            "backup_name": text("backup_name", 120),
            "data": {
                "api_address_before": router.api_address_before,
                "board": router.board_name, "serial": router.serial,
                "version": router.routeros_version,
                "reglas_firewall": [
                    "MIRABILENET ONE: gestion ICMP por WireGuard",
                    "MIRABILENET ONE: gestion API desde worker",
                    "MIRABILENET ONE: gestion SSH y Winbox por WireGuard",
                ],
            },
        })
        try:
            router._declare_peer()
        except Exception as exc:  # el peer se puede volver a declarar desde el panel
            _logger.warning("No se pudo declarar el peer de %s: %s", router.name, exc)
            Log._log("router_enrolar", "Peer no declarado: %s" % exc,
                     record=router, region=router.region_id)
        Log._log(
            "router_enrolar",
            "Router %s enrolado desde %s. Identidad=%s, serie=%s, versión=%s" % (
                router.name, ip, router.identity, router.serial, router.routeros_version),
            record=router, region=router.region_id,
            payload={"board": router.board_name, "serial": router.serial})
        return 200, {
            "estado": "recibido", "router": router.name, "wg_ip": router.wg_ip,
            "mensaje": ("Enrolamiento registrado. El router pasara a Conectado cuando los "
                        "cinco chequeos de diagnostico esten en verde."),
        }
