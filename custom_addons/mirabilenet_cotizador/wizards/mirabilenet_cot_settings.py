"""Ajustes del cotizador: credenciales de DigiCorp (cifradas) e impuestos."""
import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.mirabilenet_isp.isp import vault

from ..models.mirabilenet_cot_config import PARAM

#: Si existen estas variables de entorno, mandan sobre lo guardado en la ventana.
ENV_USER, ENV_PASS = "DIGICORP_USER", "DIGICORP_PASS"


def digicorp_credentials(env):
    """(usuario, contraseña) de DigiCorp, o (None, None) si no hay. Primero las variables de
    entorno; si no, lo guardado (cifrado) desde los ajustes."""
    if os.environ.get(ENV_USER) and os.environ.get(ENV_PASS):
        return os.environ[ENV_USER], os.environ[ENV_PASS]
    Param = env["ir.config_parameter"].sudo()
    user, token = Param.get_param(PARAM + "digicorp_user"), Param.get_param(
        PARAM + "digicorp_pass_enc")
    if not (user and token):
        return None, None
    try:
        return user, vault.decrypt(token)
    except vault.VaultError as exc:
        raise UserError(str(exc)) from exc


class MirabilenetCotSettings(models.TransientModel):
    _name = "mirabilenet.cot.settings"
    _description = "Cotizador: ajustes"

    # DigiCorp
    digicorp_user = fields.Char(string="Usuario de DigiCorp")
    digicorp_password = fields.Char(
        string="Contraseña de DigiCorp",
        help="Se guarda cifrada con la clave maestra. Déjela vacía para conservar la actual.")
    digicorp_status = fields.Char(string="Estado", readonly=True)
    # Impuestos
    taxes_enabled = fields.Boolean(
        string="Cobrar IVA + IT",
        help="Apagado: las cotizaciones nuevas salen sin factura y sin impuestos. Las ya "
             "armadas conservan lo que tenían.")
    tax_mode = fields.Selection([("agregar", "Se suman al precio (precio × 1,16)"),
                                 ("bruto", "Ya están incluidos en el precio")],
                                string="Cómo se aplican", default="agregar")
    iva_pct = fields.Float(string="IVA (%)", digits=(5, 2))
    it_pct = fields.Float(string="IT (%)", digits=(5, 2))
    invoice_default = fields.Boolean(string="Cotizar con factura por defecto")
    # Generales
    validity_days = fields.Integer(string="Vigencia (días)")
    exchange_rate = fields.Float(string="Tipo de cambio manual (Bs por USD)", digits=(12, 4))

    @api.model
    def _get(self, key):
        return self.env["mirabilenet.cot.engine"]._param(key)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        Param = self.env["ir.config_parameter"].sudo()
        if os.environ.get(ENV_USER) and os.environ.get(ENV_PASS):
            status = _("Se usan las variables de entorno %(u)s y %(p)s del servidor.",
                       u=ENV_USER, p=ENV_PASS)
        elif Param.get_param(PARAM + "digicorp_pass_enc"):
            status = _("Guardadas (contraseña cifrada).")
        else:
            status = _("Sin credenciales: el conector de DigiCorp no puede entrar.")
        res.update({
            "digicorp_user": Param.get_param(PARAM + "digicorp_user") or False,
            "digicorp_status": status,
            "taxes_enabled": self._get("impuestos_activos") in ("1", "True", "true"),
            "tax_mode": self._get("modo_impuestos"),
            "iva_pct": float(self._get("iva")) * 100,
            "it_pct": float(self._get("it")) * 100,
            "invoice_default": self._get("facturar_por_defecto") in ("1", "True", "true"),
            "validity_days": int(float(self._get("vigencia_dias"))),
            "exchange_rate": float(self._get("tipo_cambio_manual")),
        })
        return res

    def action_save(self):
        self.ensure_one()
        if not self.env.user.has_group("mirabilenet_cotizador.group_mirabilenet_cot_manager"):
            raise UserError(_("Solo quien configura el cotizador cambia estos ajustes."))
        if not (0 <= self.iva_pct < 100 and 0 <= self.it_pct < 100):
            raise UserError(_("El IVA y el IT van entre 0 y 100 %."))
        if self.validity_days < 1 or self.exchange_rate <= 0:
            raise UserError(_("La vigencia y el tipo de cambio deben ser mayores que cero."))
        Param = self.env["ir.config_parameter"].sudo()
        values = {
            "impuestos_activos": "1" if self.taxes_enabled else "0",
            "modo_impuestos": self.tax_mode,
            "iva": "%.4f" % (self.iva_pct / 100),
            "it": "%.4f" % (self.it_pct / 100),
            "facturar_por_defecto": "1" if (self.invoice_default and self.taxes_enabled) else "0",
            "vigencia_dias": str(self.validity_days),
            "tipo_cambio_manual": "%.4f" % self.exchange_rate,
            "digicorp_user": (self.digicorp_user or "").strip(),
        }
        if self.digicorp_password:
            try:
                values["digicorp_pass_enc"] = vault.encrypt(self.digicorp_password)
            except vault.VaultError as exc:
                raise UserError(str(exc)) from exc
        for key, value in values.items():
            Param.set_param(PARAM + key, value)
        # La contraseña en claro no se queda en el asistente.
        self.digicorp_password = False
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"title": _("Ajustes guardados"), "type": "success",
                           "message": _("Los cambios valen para las cotizaciones nuevas."),
                           "next": {"type": "ir.actions.act_window_close"}}}

    def action_clear_digicorp(self):
        if not self.env.user.has_group("mirabilenet_cotizador.group_mirabilenet_cot_manager"):
            raise UserError(_("Solo quien configura el cotizador cambia estos ajustes."))
        Param = self.env["ir.config_parameter"].sudo()
        Param.set_param(PARAM + "digicorp_user", False)
        Param.set_param(PARAM + "digicorp_pass_enc", False)
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"title": _("Credenciales borradas"), "type": "warning",
                           "message": _("Ya no hay credenciales de DigiCorp guardadas."),
                           "next": {"type": "ir.actions.act_window_close"}}}
