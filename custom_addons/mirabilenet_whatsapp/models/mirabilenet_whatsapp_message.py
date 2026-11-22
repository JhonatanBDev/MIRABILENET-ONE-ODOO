import logging
from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools import mute_logger

from ..whatsapp import money as calc

from ..whatsapp import phones
from ..whatsapp.gateway import WhatsAppError
from .mirabilenet_support_case import OPERATOR
from .mirabilenet_whatsapp_template import ACTIVE_EVENTS, EVENTS

_logger = logging.getLogger(__name__)

STATES = [
    ("pendiente", "Pendiente de envío"),
    ("enviado", "Enviado"),
    ("entregado", "Entregado"),
    ("leido", "Leído"),
    ("fallido", "Fallido"),
    ("descartado", "Descartado"),
]
#: Estados que cuentan como notificación hecha al cliente.
DELIVERED_STATES = ("enviado", "entregado", "leido")
#: Para no retroceder cuando Meta manda los estados desordenados.
STATE_ORDER = {"pendiente": 0, "enviado": 1, "entregado": 2, "leido": 3, "fallido": 4,
               "descartado": 4}
META_STATES = {"sent": ("enviado", "sent_at"), "delivered": ("entregado", "delivered_at"),
               "read": ("leido", "read_at"), "failed": ("fallido", None)}
#: Eventos de cobranza que una persona puede enviar a mano, con aviso de cobro.
MANUAL_EVENTS = ("aviso_emitido", "recordatorio_pago", "aviso_vencido", "recordatorio_mora")
BATCH = 200


class MirabilenetWhatsappMessage(models.Model):
    """Bandeja de salida y bitácora. Una fila por intento de notificación.

    Nada se envía directo desde los cobros: se encola una fila y una tarea la
    despacha. Así una caída de Meta no frena la emisión de avisos.
    """
    _name = "mirabilenet.whatsapp.message"
    _description = "MIRABILENET: mensaje de WhatsApp"
    _order = "id desc"
    _rec_name = "unique_key"

    partner_id = fields.Many2one("res.partner", string="Cliente", required=True,
                                 ondelete="cascade", index=True, readonly=True)
    charge_id = fields.Many2one("account.move", string="Aviso de cobro",
                                ondelete="set null", index=True, readonly=True)
    region_id = fields.Many2one("mirabilenet.region", string="Región", required=True,
                                ondelete="restrict", index=True, readonly=True)
    number_id = fields.Many2one("mirabilenet.whatsapp.number", string="Número de la sucursal",
                                ondelete="set null", readonly=True)
    template_id = fields.Many2one("mirabilenet.whatsapp.template", string="Plantilla",
                                  ondelete="set null", readonly=True)
    event = fields.Selection(EVENTS, string="Evento", required=True, index=True, readonly=True)
    destination = fields.Char(string="Destino", required=True, readonly=True)
    parameters = fields.Json(string="Parámetros enviados", readonly=True)
    header_image_url = fields.Char(string="Imagen del encabezado", readonly=True)
    state = fields.Selection(STATES, string="Estado", default="pendiente", required=True,
                             index=True, readonly=True)
    attempts = fields.Integer(string="Intentos", readonly=True)
    wa_message_id = fields.Char(string="Id del mensaje en Meta", index=True, readonly=True)
    error_code = fields.Char(string="Código de error", readonly=True)
    error_detail = fields.Char(string="Detalle del error", readonly=True)
    unique_key = fields.Char(string="Clave de deduplicación", required=True, readonly=True,
                             index=True)
    sent_at = fields.Datetime(string="Enviado", readonly=True)
    delivered_at = fields.Datetime(string="Entregado", readonly=True)
    read_at = fields.Datetime(string="Leído", readonly=True)

    _key_uniq = models.Constraint("unique(unique_key)", "Ese mensaje ya fue encolado.")

    def write(self, vals):
        if not self.env.su:
            raise UserError(_("La bitácora de mensajes no se edita."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise UserError(_("La bitácora de mensajes no se elimina."))
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise UserError(_("Los mensajes los encola el sistema."))
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Quién envía y con qué
    # ------------------------------------------------------------------
    @api.model
    def _partner_by_number(self, contact):
        """Cliente cuyo WhatsApp o teléfono coincide con el contacto (E.164 sin +)."""
        if len(contact or "") < 4:
            return self.env["res.partner"]
        tail = contact[-4:]
        candidates = self.env["res.partner"].sudo().search([
            ("mirabilenet_is_customer", "=", True),
            "|", ("mirabilenet_whatsapp", "like", tail), ("phone", "like", tail)], limit=50)
        for partner in candidates:
            try:
                if phones.normalize_number(
                        partner.mirabilenet_whatsapp or partner.phone) == contact:
                    return partner
            except phones.NotSendable:
                continue
        return self.env["res.partner"]

    @api.model
    def _sender_for(self, partner, region):
        """Remitente del cliente: el compartido si existe; si no, el de su sucursal; si no,
        uno activo de la misma región."""
        Number = self.env["mirabilenet.whatsapp.number"].sudo()
        shared = Number.search([("shared_global", "=", True)], limit=1)
        if shared:
            return shared
        branch = partner.mirabilenet_branch_id
        if branch and branch.region_id == region:
            own = Number.search([("branch_id", "=", branch.id)], limit=1)
            if own:
                return own
        neighbour = Number.search(
            [("region_id", "=", region.id), ("branch_id.active", "=", True)],
            order="branch_id", limit=1)
        if not neighbour:
            raise phones.NotSendable(
                "Ninguna sucursal de la región tiene número de WhatsApp configurado.")
        return neighbour

    @api.model
    def _branch_for(self, partner, region):
        """Sucursal que se nombra al cliente, también si el remitente es compartido."""
        branch = partner.mirabilenet_branch_id
        if branch and branch.region_id == region:
            return branch
        return self.env["mirabilenet.branch"].sudo().search(
            [("region_id", "=", region.id)], order="name", limit=1)

    @api.model
    def _charge_context(self, charge, number):
        """Todo lo que una plantilla de cobranza puede pedir, aunque use tres valores."""
        today = self.env["account.move"]._mirabilenet_today()
        partner, region, due = charge.partner_id, charge.mirabilenet_region_id, charge.invoice_date_due
        branch = self._branch_for(partner, region)
        qr = self.env["mirabilenet.payment.qr"]._current(region)
        return {
            "cliente": partner.name,
            "codigo_cliente": partner.mirabilenet_code,
            "numero_aviso": charge.name,
            "concepto": charge._mirabilenet_concept(),
            "periodo": charge.invoice_date.strftime("%m/%Y"),
            "monto": "%.2f" % calc.money(charge.amount_total),
            "saldo": "%.2f" % calc.money(charge.amount_residual),
            "moneda": charge.currency_id.name,
            "fecha_vencimiento": due.strftime("%d/%m/%Y"),
            "dias_restantes": str(max((due - today).days, 0)),
            "dias_vencido": str(max((today - due).days, 0)),
            "sucursal": branch.name or region.name,
            "telefono_sucursal": branch.phone or number.display_number,
            "url_qr": qr.public_url if qr else "",
        }

    @api.model
    def _has_consent(self, partner):
        return bool(self.env["mirabilenet.whatsapp.consent"].sudo().search_count(
            [("partner_id", "=", partner.id)]))

    @api.model
    def _daily_limit_reached(self, partner, settings):
        since = fields.Datetime.now() - timedelta(days=1)
        count = self.sudo().search_count([
            ("partner_id", "=", partner.id), ("create_date", ">=", since),
            ("state", "in", ("pendiente",) + DELIVERED_STATES)])
        return count >= settings.daily_limit

    @api.model
    def _agent_attending(self, number, destination, settings):
        """¿Una persona de la sucursal escribió a ese cliente hace poco? Solo tiene sentido
        en coexistencia: en API pura nadie más escribe por ese número."""
        if number.mode != "coexistencia" or not settings.silence_hours:
            return False
        since = fields.Datetime.now() - timedelta(hours=settings.silence_hours)
        return bool(self.env["mirabilenet.whatsapp.agent.activity"].sudo().search_count([
            ("number_id", "=", number.id), ("contact", "=", destination),
            ("last_message_at", ">=", since)]))

    # ------------------------------------------------------------------
    # Encolar y despachar
    # ------------------------------------------------------------------
    @api.model
    def _enqueue(self, event, charge=None, partner=None, extra_key=""):
        """Deja el mensaje listo para despachar. Devuelve vacío, sin fallar, cuando no toca
        enviar: mensajería apagada, baja, sin consentimiento, sin número, tope diario, una
        persona atendiendo, o ya encolado. Quien emite avisos no debe romperse por eso."""
        Message = self.sudo()
        settings = self.env["mirabilenet.whatsapp.settings"]._load()
        if not settings.active_messaging:
            return Message
        if event not in ACTIVE_EVENTS:
            raise phones.NotSendable("El evento «%s» no tiene gancho activo." % event)
        charge = charge.sudo() if charge else self.env["account.move"].sudo()
        partner = (partner or charge.partner_id).sudo()
        if not partner:
            raise phones.NotSendable("Hace falta un cliente o un aviso de cobro.")
        if self.env["mirabilenet.whatsapp.optout"].sudo().search_count(
                [("partner_id", "=", partner.id)]):
            return Message
        # El consentimiento va antes que todo lo de Meta: escribir a quien no lo autorizó
        # hace que reporten el número, y un número reportado se pierde para la sucursal.
        if settings.require_consent and not self._has_consent(partner):
            _logger.info("WhatsApp omitido para %s: sin consentimiento", partner.id)
            return Message
        region = charge.mirabilenet_region_id or partner.mirabilenet_region_id
        try:
            destination = phones.normalize_number(
                partner.mirabilenet_whatsapp or partner.phone)
            number = self._sender_for(partner, region)
            template = self.env["mirabilenet.whatsapp.template"]._for(event, region)
            if not template:
                raise phones.NotSendable(
                    "No hay plantilla activa para el evento «%s»." % event)
        except phones.NotSendable as exc:
            # Un cliente sin número no puede frenar la emisión del resto del período.
            _logger.info("WhatsApp omitido para %s: %s", partner.id, exc)
            return Message
        if self._daily_limit_reached(partner, settings):
            _logger.info("WhatsApp omitido para %s: tope diario", partner.id)
            return Message
        if self._agent_attending(number, destination, settings):
            _logger.info("WhatsApp omitido para %s: lo atiende una persona", partner.id)
            return Message
        if charge:
            context = self._charge_context(charge, number)
        else:
            branch = self._branch_for(partner, region)
            context = {"cliente": partner.name, "sucursal": branch.name or region.name}
        header = ""
        if template.qr_header:
            qr = self.env["mirabilenet.payment.qr"]._current(region)
            if not qr:
                _logger.error("WhatsApp %s no encolado: falta el QR vigente de la región %s",
                              event, region.id)
                return Message
            header = qr.public_url
        # La clave lleva el objeto de origen, no la fecha: repetir la tarea del día no
        # vuelve a escribir al cliente.
        anchor = charge.name if charge else partner.mirabilenet_code
        key = "%s:%s%s" % (event, anchor, (":%s" % extra_key) if extra_key else "")
        if Message.search_count([("unique_key", "=", key)]):
            return Message
        try:
            with mute_logger("odoo.sql_db"), self.env.cr.savepoint():
                return Message.create({
                    "partner_id": partner.id, "charge_id": charge.id, "region_id": region.id,
                    "number_id": number.id, "template_id": template.id, "event": event,
                    "destination": destination,
                    "parameters": [phones.clean_parameter(context.get(name))
                                   for name in template._variable_list()],
                    "header_image_url": header or False, "unique_key": key,
                })
        except IntegrityError:
            return Message  # otro proceso ya lo encoló: es el caso normal

    def _dispatch(self):
        """Entrega cada mensaje pendiente a Meta y anota el resultado."""
        Settings = self.env["mirabilenet.whatsapp.settings"]
        settings = Settings._load()
        gateway = Settings._gateway()
        for message in self.sudo().filtered(lambda m: m.state == "pendiente"):
            if not settings.active_messaging or not settings.configured:
                message.error_detail = _("La mensajería está apagada o sin credenciales.")
                continue
            number = message.number_id
            if not number or not number.active:
                message.write({"state": "descartado",
                               "error_detail": _("La sucursal ya no tiene número activo.")})
                continue
            if self.env["mirabilenet.whatsapp.optout"].sudo().search_count(
                    [("partner_id", "=", message.partner_id.id)]):
                message.write({"state": "descartado",
                               "error_detail": _("Cliente dado de baja.")})
                continue
            attempts = message.attempts + 1
            if settings.test_mode:
                # No se contacta a Meta: queda como enviado para revisar el texto.
                message.write({"state": "enviado", "wa_message_id": "modo-prueba",
                               "sent_at": fields.Datetime.now(), "attempts": attempts})
                continue
            template = message.template_id
            try:
                wa_id = gateway.send_template(
                    phone_number_id=number.phone_number_id,
                    token=settings._secret("access_token"),
                    destino=message.destination, plantilla=template.meta_name,
                    idioma=template.language, parametros=message.parameters or [],
                    header_image_url=message.header_image_url or "",
                    requiere_imagen_encabezado=template.qr_header,
                    parameter_format=template.parameter_format,
                    parameter_names=template._variable_list(),
                    api_version=settings.api_version)
            except WhatsAppError as exc:
                exhausted = attempts >= settings.max_retries
                message.write({
                    "attempts": attempts, "error_code": exc.codigo or False,
                    "error_detail": str(exc)[:500],
                    "state": "pendiente" if exc.reintentable and not exhausted else "fallido"})
                number.last_error = str(exc)[:255]
                continue
            message.write({"state": "enviado", "wa_message_id": wa_id, "attempts": attempts,
                           "sent_at": fields.Datetime.now(), "error_code": False,
                           "error_detail": False})
            number.write({"verified_at": fields.Datetime.now(), "last_error": False})
            self.env["mirabilenet.audit.log"]._log(
                "crear", "WhatsApp %s a %s desde %s" % (
                    dict(EVENTS)[message.event], message.destination, number.branch_id.name),
                record=message, region=message.region_id)
        return True

    @api.model
    def _trigger_dispatch(self):
        self.env.ref("mirabilenet_whatsapp.cron_dispatch_pending").sudo()._trigger()

    @api.model
    def _apply_meta_status(self, status):
        """Estado de entrega que informa Meta. Nunca retrocede."""
        wa_id, name = status.get("id") or "", status.get("status") or ""
        if not wa_id or name not in META_STATES:
            return False
        message = self.sudo().search([("wa_message_id", "=", wa_id)], limit=1)
        new, stamp = META_STATES[name]
        if not message:
            return self.env["mirabilenet.conversation.message"]._apply_meta_status(
                wa_id, new, status)
        if STATE_ORDER[new] <= STATE_ORDER[message.state] and new != "fallido":
            return False
        vals = {"state": new}
        if stamp:
            vals[stamp] = fields.Datetime.now()
        if new == "fallido":
            error = (status.get("errors") or [{}])[0]
            vals.update(error_code=str(error.get("code") or "") or False,
                        error_detail=str(error.get("title") or error.get("message")
                                         or "")[:500] or False)
        message.write(vals)
        return True

    # ------------------------------------------------------------------
    # Tareas programadas
    # ------------------------------------------------------------------
    @api.model
    def _collection_delegated(self):
        """Si n8n lleva la cobranza, estas tareas no encolan recordatorios."""
        return self.env["ir.config_parameter"].sudo().get_param(
            "mirabilenet.n8n_controls_collection") in ("1", "true", "True")

    @api.model
    def _cron_dispatch_pending(self):
        """Fuera del horario los mensajes esperan en cola: no se pierden ni se envían."""
        settings = self.env["mirabilenet.whatsapp.settings"]._load()
        if not settings.active_messaging or not settings._in_window():
            return 0
        pending = self.sudo().search(
            [("state", "=", "pendiente"), ("attempts", "<", settings.max_retries)],
            order="id", limit=BATCH)
        pending._dispatch()
        return len(pending)

    @api.model
    def _open_charges(self, domain):
        Move = self.env["account.move"].sudo()
        return Move.search(Move._mirabilenet_open_domain() + domain)

    @api.model
    def _cron_reminders(self):
        """Recordatorio N días antes del vencimiento. Uno por aviso, aunque se repita."""
        settings = self.env["mirabilenet.whatsapp.settings"]._load()
        if self._collection_delegated() or not settings.active_messaging:
            return 0
        target = self.env["account.move"]._mirabilenet_today() + timedelta(
            days=settings.reminder_days)
        charges = self._open_charges([
            ("invoice_date_due", "=", target)])
        return sum(1 for c in charges if self._enqueue("recordatorio_pago", charge=c))

    @api.model
    def _cron_overdue(self):
        """Aviso de mora de los cargos que ya vencieron."""
        settings = self.env["mirabilenet.whatsapp.settings"]._load()
        if self._collection_delegated() or not settings.active_messaging:
            return 0
        today = self.env["account.move"]._mirabilenet_today()
        charges = self._open_charges([("invoice_date_due", "<", today)])
        return sum(1 for c in charges if self._enqueue("aviso_vencido", charge=c))

    @api.model
    def _cron_mora_retries(self):
        """Recordatorios espaciados de una deuda que sigue vencida, con tope."""
        settings = self.env["mirabilenet.whatsapp.settings"]._load()
        if self._collection_delegated() or not settings.active_messaging:
            return 0
        today = self.env["account.move"]._mirabilenet_today()
        interval = timedelta(days=settings.mora_interval_days)
        Message = self.sudo()
        sent = 0
        for charge in self._open_charges([("invoice_date_due", "<", today)]):
            previous = Message.search(
                [("charge_id", "=", charge.id), ("event", "=", "recordatorio_mora")])
            if len(previous) >= settings.mora_max_reminders:
                continue
            first = Message.search(
                [("charge_id", "=", charge.id), ("event", "=", "aviso_vencido")],
                order="id desc", limit=1)
            reference = (previous | first).sorted("create_date")[-1:]
            if reference and (reference.state == "pendiente"
                              or reference.create_date > fields.Datetime.now() - interval):
                continue
            if not reference and charge.invoice_date_due > today - interval:
                continue
            if self._enqueue("recordatorio_mora", charge=charge,
                             extra_key="mora-%s" % today.isoformat()):
                sent += 1
        return sent

    # ------------------------------------------------------------------
    # Envío manual desde la bandeja
    # ------------------------------------------------------------------
    @api.model
    def _send_manual(self, charge, event):
        """Una persona decide enviar un aviso. Sale ya, sin esperar el ciclo, pero no se
        salta consentimiento, bajas, tope diario, silencio ni región."""
        if not self.env.su and not self.env.user.has_group(OPERATOR):
            raise AccessError(_("Su rol no envía avisos por WhatsApp."))
        charge = charge.with_env(self.env)
        charge.check_access("read")
        if event not in MANUAL_EVENTS:
            raise UserError(_("Ese tipo de aviso no se envía a mano."))
        today = self.env["account.move"]._mirabilenet_today()
        if not charge.sudo()._mirabilenet_is_open():
            raise UserError(_("El aviso %s no tiene saldo pendiente.", charge.name))
        overdue = charge.invoice_date_due < today
        if event in ("aviso_vencido", "recordatorio_mora") and not overdue:
            raise UserError(_("El aviso %s todavía no venció.", charge.name))
        if event == "recordatorio_pago" and overdue:
            raise UserError(_("El aviso %s ya venció: use un aviso de mora.", charge.name))
        stamp = fields.Datetime.now().strftime("%Y%m%d%H%M%S")
        message = self._enqueue(event, charge=charge,
                                extra_key="manual-%s-%s" % (self.env.uid, stamp))
        if not message:
            raise UserError(_(
                "No se puede enviar a este cliente ahora: revise que la mensajería esté "
                "activa, que tenga WhatsApp y consentimiento, que no se haya dado de baja, "
                "que no supere el tope diario y que exista una plantilla para ese aviso."))
        self.env["mirabilenet.audit.log"]._log(
            "crear", "Envío manual de %s para %s" % (dict(EVENTS)[event], charge.name),
            record=message, region=message.region_id)
        message._dispatch()
        return message.with_env(self.env)


class MirabilenetWhatsappMessageWebhook(models.Model):
    _inherit = "mirabilenet.whatsapp.message"

    @api.model
    def _process_webhook(self, body):
        """Cuerpo ya autenticado del webhook de Meta."""
        from ..controllers.main import process_webhook
        return process_webhook(self.sudo(), body if isinstance(body, dict) else {})
