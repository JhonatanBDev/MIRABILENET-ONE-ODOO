import datetime
import logging
import os

import pytz

from odoo import SUPERUSER_ID, api, models, modules, tools, _
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from ..siat import errors as siat_errors
from ..siat.vault import Vault

_logger = logging.getLogger(__name__)

# Toda fecha fiscal se expresa en hora de Bolivia, con zona explícita.
FISCAL_TZ = pytz.timezone("America/La_Paz")


class MiraSiatService(models.AbstractModel):
    """Utilidades compartidas por el dominio fiscal: reloj fiscal, bóveda,
    autorización explícita, auditoría y traducción de errores."""
    _name = "mira.siat.service"
    _description = "Mira_Sale SIAT: servicios internos"

    # ---- bóveda -----------------------------------------------------------
    @api.model
    def _master_key(self):
        key = os.environ.get("MIRA_SIAT_MASTER_KEY")
        if not key:
            try:
                key = tools.config.get("mira_siat_master_key")
            except Exception:  # la opción puede no existir en el archivo
                key = None
        return key

    @api.model
    def _vault(self):
        return Vault(self._master_key())

    # ---- reloj fiscal -----------------------------------------------------
    @api.model
    def _fiscal_now(self):
        return datetime.datetime.now(FISCAL_TZ)

    @api.model
    def _fiscal_iso(self, dt):
        """yyyy-MM-ddTHH:mm:ss.SSS en hora de Bolivia."""
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        dt = dt.astimezone(FISCAL_TZ)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + "%03d" % (dt.microsecond // 1000)

    @api.model
    def _to_utc_naive(self, dt):
        if dt is None:
            return False
        if dt.tzinfo is None:
            dt = FISCAL_TZ.localize(dt)
        return dt.astimezone(pytz.utc).replace(tzinfo=None)

    # ---- errores ----------------------------------------------------------
    @api.model
    def _user_error(self, exc):
        """Convierte un SiatError en un mensaje accionable para la interfaz."""
        lines = ["[%s] %s" % (exc.code, exc.message)]
        for detail in exc.details or []:
            if isinstance(detail, dict):
                detail = "%s: %s" % (detail.get("code", ""), detail.get("description", ""))
            lines.append("  - %s" % detail)
        if exc.action:
            lines.append(_("Qué hacer: %s", exc.action))
        return UserError("\n".join(lines))

    # ---- autorización explícita ------------------------------------------
    @api.model
    def _require_group(self, group_xmlid, action):
        """Todo punto sensible exige permiso explícito, no solo sesión iniciada."""
        if self.env.su or self.env.user.has_group(group_xmlid):
            return
        self._audit_independent(action + ".denied")
        raise AccessError(_(
            "[%(code)s] No tiene permiso para esta operación (%(action)s).",
            code=siat_errors.AUTH, action=action))

    # ---- auditoría --------------------------------------------------------
    @api.model
    def _client_ip(self):
        try:
            return request.httprequest.remote_addr if request else False
        except RuntimeError:
            return False

    @api.model
    def _audit(self, action, record=None, before=None, after=None, company=None,
               correlation_id=None):
        company = company or (
            record.company_id if record is not None and "company_id" in record._fields
            else self.env.company)
        return self.env["mira.siat.audit.log"].sudo().create({
            "company_id": company.id,
            "user_id": self.env.uid,
            "action": action,
            "res_model": record._name if record is not None else False,
            "res_id": record.id if record is not None and len(record) == 1 else False,
            "before_json": before or False,
            "after_json": after or False,
            "ip": self._client_ip(),
            "correlation_id": correlation_id or False,
        })

    @api.model
    def _audit_independent(self, action):
        """Auditoría que sobrevive al rollback (por ejemplo, un acceso denegado)."""
        vals = {
            "company_id": self.env.company.id,
            "user_id": self.env.uid,
            "action": action,
            "ip": self._client_ip(),
        }
        if modules.module.current_test:
            self.env["mira.siat.audit.log"].sudo().create(vals)
            return
        try:
            with self.env.registry.cursor() as cr:
                api.Environment(cr, SUPERUSER_ID, {})["mira.siat.audit.log"].create(vals)
        except Exception:
            _logger.exception("No se pudo registrar la auditoría de %s", action)

    # ---- transacción ------------------------------------------------------
    @api.model
    def _commit(self):
        """Fija en base de datos el documento antes de hablar con el SIN, para
        que un fallo posterior nunca deje una factura aceptada sin registro."""
        if not modules.module.current_test:
            self.env.cr.commit()
