import re
from datetime import datetime, time

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

#: El día de cupo de Google empieza a la medianoche del Pacífico, no de La Paz.
QUOTA_ZONE = pytz.timezone("America/Los_Angeles")
MODEL_PATTERN = re.compile(r"^models/[a-z0-9][a-z0-9.\-]{2,50}$")
SALES_STYLE = (
    "Actúa como un vendedor con iniciativa: no te limites a informar, guía a la persona hasta "
    "dejar sus datos.\n"
    "- Primero descubre la necesidad: para qué usa internet, cuántas personas y dispositivos, "
    "qué le falla hoy.\n"
    "- Presenta el plan que le conviene por su beneficio (qué va a poder hacer) antes que por "
    "su precio.\n"
    "- Si pone una objeción (precio, lo voy a pensar, ya tengo otro proveedor), reconócela y "
    "respóndela con datos reales de los planes y la cobertura. Rebate como máximo dos "
    "objeciones.\n"
    "- Cierra cada mensaje con una pregunta o un siguiente paso concreto (¿en qué zona vives?, "
    "¿te registro para que un asesor coordine la instalación?).\n"
    "- Ante un «no» claro, agradece, deja la puerta abierta y no insistas más."
)
SUPPORT_STYLE = (
    "Sé resolutivo y cálido. Cuando un cliente quiera cancelar el servicio, intenta que se "
    "quede, una sola vez:\n"
    "- Muestra empatía y pregunta el motivo si no lo dijo.\n"
    "- Si el motivo es un problema que se puede resolver (falla técnica, duda con un cobro), "
    "ofrece resolverlo.\n"
    "- Si hay promociones de retención, ofrece la que mejor responda a su motivo y explica sus "
    "condiciones.\n"
    "- Recuérdale lo que ya tiene con nosotros, sin exagerar ni hablar mal de otros "
    "proveedores.\n"
    "- Si insiste en cancelar o rechaza la oferta, respétalo y pasa su solicitud sin más "
    "intentos."
)


class MirabilenetBotSettings(models.Model):
    """Interruptores y modelo de los asistentes con IA de n8n. Un solo registro, que cambia
    solo quien tiene alcance global.

    El cupo de Google no se puede consultar: lo que se muestra es lo medido aquí (respuestas
    por modelo) y lo que Google respondió (agotado), nunca una estimación.
    """
    _name = "mirabilenet.bot.settings"
    _description = "MIRABILENET: ajustes del asistente con IA"

    name = fields.Char(default="Asistente con IA", readonly=True)
    support_on = fields.Boolean(string="Asistente de soporte activo", default=True)
    sales_on = fields.Boolean(string="Asistente de ventas activo", default=True)
    model = fields.Char(string="Modelo principal", default="models/gemini-flash-lite-latest",
                        required=True)
    backup_model = fields.Char(string="Modelo de respaldo",
                               default="models/gemini-flash-latest")
    daily_limit = fields.Integer(
        string="Límite diario de respuestas por modelo",
        help="Tope propio por modelo y día de Google. Cero: sin tope propio.")
    sales_style = fields.Text(string="Estilo del asistente de ventas", default=SALES_STYLE)
    support_style = fields.Text(string="Estilo del asistente de soporte",
                                default=SUPPORT_STYLE)
    about_us = fields.Text(
        string="Quiénes somos",
        help="Lo que el asistente dice si le preguntan quiénes somos. Solo datos reales: no "
             "agrega nada.")
    exhausted = fields.Json(string="Modelos agotados", readonly=True)
    in_use = fields.Char(string="Modelo en uso", compute="_compute_usage")
    usage_summary = fields.Text(string="Uso del día", compute="_compute_usage")

    @api.model
    def _load(self):
        settings = self.sudo().search([], limit=1, order="id")
        return settings or self.sudo().create({})

    @api.constrains("model", "backup_model", "sales_style", "support_style", "about_us",
                    "daily_limit")
    def _check_settings(self):
        for settings in self:
            for name in filter(None, (settings.model, settings.backup_model)):
                if not MODEL_PATTERN.match(name):
                    raise ValidationError(_(
                        "Use el nombre del modelo tal como lo da Google, por ejemplo "
                        "models/gemini-flash-lite-latest."))
            if settings.backup_model and settings.backup_model == settings.model:
                raise ValidationError(_("El respaldo tiene que ser otro modelo."))
            if max(len(settings.sales_style or ""), len(settings.support_style or "")) > 2000:
                raise ValidationError(_("El estilo admite hasta 2000 caracteres."))
            if len(settings.about_us or "") > 1500:
                raise ValidationError(_("«Quiénes somos» admite hasta 1500 caracteres."))
            if settings.daily_limit < 0:
                raise ValidationError(_("El límite diario no puede ser negativo."))

    def _require_global(self):
        user = self.env.user
        if self.env.su or user._mirabilenet_is_super():
            return
        if not user.mirabilenet_is_global or user.mirabilenet_role == "auditor":
            raise AccessError(_(
                "Solo un usuario con alcance global cambia los ajustes del asistente."))

    @api.model_create_multi
    def create(self, vals_list):
        if self.sudo().search_count([]):
            raise UserError(_("Los ajustes del asistente son un solo registro."))
        return super().create(vals_list)

    def write(self, vals):
        self._require_global()
        result = super().write(vals)
        if not self.env.su:
            self.env["mirabilenet.audit.log"]._log(
                "modificar", "Ajustes del asistente con IA modificados: %s"
                % ", ".join(sorted(vals)), record=self[:1])
        return result

    def unlink(self):
        raise UserError(_("Los ajustes del asistente no se eliminan."))

    # -- Cupo -----------------------------------------------------------
    @api.model
    def _quota_day(self, now=None):
        now = now or fields.Datetime.now()
        return pytz.utc.localize(now).astimezone(QUOTA_ZONE).date()

    @api.model
    def _quota_day_start(self, now=None):
        start = QUOTA_ZONE.localize(datetime.combine(self._quota_day(now), time(0)))
        return start.astimezone(pytz.utc).replace(tzinfo=None)

    def _answers_today(self, model, now=None):
        """Respuestas que el asistente mandó hoy (día de Google) con ese modelo."""
        if not model:
            return 0
        self.env.cr.execute(
            "SELECT count(*) FROM mirabilenet_conversation_message WHERE origin = 'bot' "
            "AND direction = 'saliente' AND create_date >= %s AND data->>'modelo' = %s",
            [self._quota_day_start(now), model])
        return self.env.cr.fetchone()[0]

    def _exhausted_today(self, model, now=None):
        mark = (self.exhausted or {}).get(model) or {}
        return mark if mark.get("dia") == self._quota_day(now).isoformat() else None

    def _model_state(self, model, now=None):
        self.ensure_one()
        used = self._answers_today(model, now)
        exhausted = self._exhausted_today(model, now)
        at_limit = bool(self.daily_limit) and used >= self.daily_limit
        return {"modelo": model, "respuestas_hoy": used, "limite": self.daily_limit or None,
                "agotado": exhausted is not None, "al_limite": at_limit,
                "disponible": bool(model) and exhausted is None and not at_limit}

    def _model_to_use(self, now=None):
        """El principal si está disponible; si no, el respaldo; si tampoco, nada."""
        self.ensure_one()
        for model in (self.model, self.backup_model):
            if model and self._model_state(model, now)["disponible"]:
                return model
        return None

    @api.model
    def _for_event(self, now=None):
        """Lo que viaja a n8n con cada mensaje: qué asistentes atienden y con qué modelo."""
        settings = self._load()
        model = settings._model_to_use(now)
        return {"soporte": settings.support_on, "ventas": settings.sales_on,
                "modelo": model or "", "disponible": model is not None}

    @api.model
    def _mark_exhausted(self, model, detail="", now=None):
        """Google respondió que no hay más cupo hoy. True si es la primera vez del día."""
        settings = self._load()
        now = now or fields.Datetime.now()
        self.env.cr.execute(
            "SELECT id FROM mirabilenet_bot_settings WHERE id = %s FOR UPDATE", [settings.id])
        settings.invalidate_recordset(["exhausted"])
        if settings._exhausted_today(model, now):
            return False
        marks = dict(settings.exhausted or {})
        day = self._quota_day(now).isoformat()
        marks[model] = {"dia": day, "desde": now.isoformat(), "detalle": (detail or "")[:300]}
        settings.exhausted = marks
        following = settings._model_to_use(now)
        self.env["mirabilenet.integration.alert"]._raise(
            "ia-agotado:%s:%s" % (model, day), "Bot con IA", model,
            "Google respondió que el modelo %s no tiene más cupo hoy. %s" % (
                model, ("El bot sigue con %s." % following) if following else
                "No queda otro modelo disponible: el bot responde sin IA hasta que Google "
                "reponga el cupo."))
        return True

    def action_retry_model(self):
        """Quita la marca de agotado a mano (por ejemplo, tras activar facturación en Google)."""
        self._require_global()
        self.sudo().exhausted = {}
        return True

    @api.model
    def _style_for(self, conversation):
        settings = self._load()
        text = settings.support_style if conversation.partner_id else settings.sales_style
        return (text or "").strip()[:2000]

    @api.depends("model", "backup_model", "exhausted", "daily_limit")
    def _compute_usage(self):
        for settings in self:
            settings.in_use = settings._model_to_use() or ""
            lines = []
            for model in filter(None, (settings.model, settings.backup_model)):
                state = settings._model_state(model)
                limit = state["limite"]
                lines.append("%s: %d respuestas hoy%s%s" % (
                    model, state["respuestas_hoy"],
                    (" de %d" % limit) if limit else " (sin tope propio: —)",
                    " · AGOTADO según Google" if state["agotado"] else ""))
            settings.usage_summary = "\n".join(lines)
