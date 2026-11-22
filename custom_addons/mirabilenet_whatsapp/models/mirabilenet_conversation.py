import base64
import logging
import uuid
from datetime import timedelta

import pytz
from psycopg2 import IntegrityError

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools import mute_logger

from ..whatsapp import content, phones
from ..whatsapp.content import SendRejected
from .mirabilenet_support_case import OPERATOR

_logger = logging.getLogger(__name__)


#: Frases con las que un cliente pide dar de baja el servicio (no los mensajes).
CANCEL_PHRASES = ("cancelar servicio", "cancelar el servicio", "cancelar mi servicio",
                  "dar de baja", "baja del servicio")
HELP_WORDS = ("asesor", "ayuda", "soporte", "humano")


def local_iso(env, moment):
    """Fecha y hora con el desfase de Bolivia, como las recibía n8n."""
    if not moment:
        return None
    tz = pytz.timezone(env["ir.config_parameter"].sudo().get_param(
        "mirabilenet.timezone", "America/La_Paz"))
    return pytz.utc.localize(moment).astimezone(tz).isoformat()


class MirabilenetConversation(models.Model):
    """Hilo con un contacto en un canal. Una fila por canal y contacto.

    Odoo es la única puerta: registra cada mensaje entrante, se lo pasa a n8n ya
    normalizado y es quien envía las respuestas. n8n nunca tiene el token de Meta
    ni acceso a la base.
    """
    _name = "mirabilenet.conversation"
    _description = "MIRABILENET: conversación"
    _order = "last_incoming_at desc, id desc"
    _rec_name = "contact"

    channel = fields.Selection([("whatsapp", "WhatsApp"), ("simulador", "Simulador")],
                               string="Canal", required=True, readonly=True)
    contact = fields.Char(string="Contacto", required=True, readonly=True, index=True)
    partner_id = fields.Many2one("res.partner", string="Cliente", ondelete="set null",
                                 readonly=True, index=True)
    region_id = fields.Many2one("mirabilenet.region", string="Región", ondelete="restrict",
                                readonly=True, index=True)
    number_id = fields.Many2one("mirabilenet.whatsapp.number", string="Número de la sucursal",
                                ondelete="set null", readonly=True)
    state = fields.Selection(
        [("bot", "Atiende el asistente"), ("humano", "Atiende una persona"),
         ("cerrada", "Cerrada")], string="Estado", default="bot", required=True, index=True,
        readonly=True)
    attended_by = fields.Many2one("res.users", string="Atendida por", readonly=True)
    last_incoming_at = fields.Datetime(string="Último mensaje del contacto", readonly=True)
    last_outgoing_at = fields.Datetime(string="Última respuesta", readonly=True)
    reviewed_at = fields.Datetime(string="Revisada", readonly=True)
    message_ids = fields.One2many("mirabilenet.conversation.message", "conversation_id",
                                  string="Mensajes")
    window_until = fields.Datetime(string="Ventana de 24 h hasta",
                                   compute="_compute_window")
    window_open = fields.Boolean(string="Ventana abierta", compute="_compute_window")
    pending_review = fields.Boolean(string="Sin revisar", compute="_compute_pending_review",
                                    search="_search_pending_review")

    _pair_uniq = models.Constraint(
        "unique(channel, contact)", "Ya existe una conversación con ese contacto.")

    @api.depends("last_incoming_at")
    def _compute_window(self):
        now = fields.Datetime.now()
        for conversation in self:
            until = (conversation.last_incoming_at + timedelta(hours=content.WINDOW_HOURS)
                     if conversation.last_incoming_at else False)
            conversation.window_until = until
            conversation.window_open = bool(until and until > now)

    @api.depends("last_incoming_at", "reviewed_at")
    def _compute_pending_review(self):
        for conversation in self:
            conversation.pending_review = bool(
                conversation.last_incoming_at and (
                    not conversation.reviewed_at
                    or conversation.reviewed_at < conversation.last_incoming_at))

    def _search_pending_review(self, operator, value):
        truthy = any(value) if isinstance(value, (list, tuple, set)) else bool(value)
        positive = truthy if operator in ("=", "in") else not truthy
        self.flush_model(["last_incoming_at", "reviewed_at"])
        self.env.cr.execute(
            "SELECT id FROM mirabilenet_conversation WHERE last_incoming_at IS NOT NULL "
            "AND (reviewed_at IS NULL OR reviewed_at < last_incoming_at)")
        ids = [row[0] for row in self.env.cr.fetchall()]
        return [("id", "in" if positive else "not in", ids)]

    def _window_is_open(self):
        self.ensure_one()
        last = self.sudo().last_incoming_at
        return bool(last and last + timedelta(hours=content.WINDOW_HOURS)
                    > fields.Datetime.now())

    def write(self, vals):
        if not self.env.su:
            raise UserError(_("Una conversación no se edita: se atiende con sus acciones."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise UserError(_("Las conversaciones no se eliminan."))
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise UserError(_("Las conversaciones las abre el sistema al llegar un mensaje."))
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Entrantes
    # ------------------------------------------------------------------
    @api.model
    def _register_incoming(self, channel, contact, kind, text="", data=None, external_id=None,
                           number=None, partner=None, region=None, moment=None):
        """Guarda el mensaje y abre (o reabre) la conversación. Devuelve
        (conversación, mensaje, creado). Si el canal repite el mensaje, no se duplica."""
        Message = self.env["mirabilenet.conversation.message"].sudo()
        moment = moment or fields.Datetime.now()
        previous = Message.search([("external_id", "=", external_id)], limit=1)
        if previous:
            return previous.conversation_id, previous, False
        partner = partner or self.env["mirabilenet.whatsapp.message"]._partner_by_number(contact)
        region = region or partner.sudo().mirabilenet_region_id or (
            number.region_id if number else self.env["mirabilenet.region"])
        Conversation = self.sudo()
        conversation = Conversation.search(
            [("channel", "=", channel), ("contact", "=", contact)], limit=1)
        if not conversation:
            try:
                with mute_logger("odoo.sql_db"), self.env.cr.savepoint():
                    conversation = Conversation.create({
                        "channel": channel, "contact": contact, "partner_id": partner.id,
                        "region_id": region.id})
            except IntegrityError:
                conversation = Conversation.search(
                    [("channel", "=", channel), ("contact", "=", contact)], limit=1)
        self.env.cr.execute(
            "SELECT id FROM mirabilenet_conversation WHERE id = %s FOR UPDATE",
            [conversation.id])
        vals = {}
        if not conversation.last_incoming_at or moment > conversation.last_incoming_at:
            vals["last_incoming_at"] = moment
        if conversation.state == "cerrada":
            vals.update(state="bot", attended_by=False)
        if partner and conversation.partner_id != partner:
            vals["partner_id"] = partner.id
        if region and conversation.region_id != region:
            vals["region_id"] = region.id
        if number and conversation.number_id != number:
            vals["number_id"] = number.id
        if vals:
            conversation.write(vals)
        try:
            with mute_logger("odoo.sql_db"), self.env.cr.savepoint():
                message = Message.create({
                    "conversation_id": conversation.id, "direction": "entrante",
                    "origin": "contacto", "kind": kind, "text": text or False,
                    "data": data or {}, "external_id": external_id})
        except IntegrityError:
            return conversation, Message.search([("external_id", "=", external_id)],
                                                limit=1), False
        return conversation, message, True

    def _event(self, message, handled=None, proof=None):
        """Lo que recibe n8n por cada mensaje, sin datos del cliente: solo si es cliente.
        Para consultar algo usa las herramientas con el id de la conversación."""
        self.ensure_one()
        data = message.data or {}
        return {
            "evento": "mensaje_entrante",
            "mensaje_id": message.id,
            "canal": self.channel,
            "conversacion": {"id": self.id, "estado": self.state,
                             "ventana_hasta": local_iso(self.env, self.window_until)},
            "contacto": {"telefono": self.contact, "es_cliente": bool(self.partner_id)},
            "mensaje": {
                "tipo": message.kind, "texto": message.text or "",
                "opcion_id": data.get("opcion_id", ""),
                "ubicacion": {k: data[k] for k in ("latitud", "longitud", "nombre",
                                                    "direccion") if k in data} or None,
                "mime": data.get("mime", ""),
            },
            "manejado_por_sistema": handled,
            "ia": self.env["mirabilenet.bot.settings"]._for_event(),
            "comprobante": proof,
            "recibido_at": local_iso(self.env, message.create_date),
        }

    def _notify_n8n(self, message, handled=None, proof=None):
        """Deja el evento para entregarlo a n8n en segundo plano."""
        self.ensure_one()
        Event = self.env["mirabilenet.n8n.event"]
        if not Event._configured():
            return Event
        return Event._enqueue(self._event(message, handled, proof))

    # ------------------------------------------------------------------
    # Salientes
    # ------------------------------------------------------------------
    def _enqueue_outgoing(self, kind, content_data, key, origin="bot", attachment=None):
        """Valida las reglas y deja la respuesta lista para despachar. Devuelve
        (mensaje, creado); con la misma clave devuelve el mensaje anterior.

        Las respuestas no son avisos de la empresa: contestan algo que el contacto acaba
        de escribir, así que no esperan el horario ni cuentan para el tope diario. Sí
        exigen la ventana de 24 h, que no atienda una persona, que no haya baja, una clave
        por envío y el tope por hora.
        """
        self.ensure_one()
        conversation = self.sudo()
        Message = self.env["mirabilenet.conversation.message"].sudo()
        key = content.clean_text(key, 120)
        if not key:
            raise SendRejected("falta_clave", "Falta la clave del envio.")
        previous = Message.search([("unique_key", "=", key)], limit=1)
        if previous:
            if previous.conversation_id != conversation:
                raise SendRejected("clave_en_uso", "La clave ya se uso en otra conversacion.")
            return previous, False
        if attachment:
            if kind not in ("imagen", "documento"):
                raise ValueError("Tipo no soportado: use texto, botones o lista.")
            body = {"texto": content.clean_text((content_data or {}).get("texto"),
                                                content.MAX_ATTACHMENT_TEXT),
                    "archivo_nombre": attachment["name"], "mime": attachment["mime"]}
        else:
            body = content.validate_content(kind, content_data)
        if origin == "bot" and conversation.state != "bot":
            raise SendRejected(
                "atiende_una_persona" if conversation.state == "humano" else "cerrada",
                "La conversacion no la esta atendiendo el bot.")
        if conversation.partner_id and self.env["mirabilenet.whatsapp.optout"].sudo(
        ).search_count([("partner_id", "=", conversation.partner_id.id)]):
            raise SendRejected("dado_de_baja", "El contacto pidio no recibir mensajes.")
        if not conversation._window_is_open():
            raise SendRejected(
                "fuera_de_ventana",
                "Pasaron mas de 24 horas desde el ultimo mensaje del contacto: solo se "
                "puede escribir con una plantilla.")
        if conversation.channel == "whatsapp":
            if not self.env["mirabilenet.whatsapp.settings"]._load().active_messaging:
                raise SendRejected("mensajeria_apagada",
                                   "La mensajeria esta desactivada en Ajustes.")
            if not conversation.number_id:
                raise SendRejected("sin_numero",
                                   "La conversacion no tiene numero de sucursal.")
        if origin == "bot" and Message.search_count([
                ("conversation_id", "=", conversation.id), ("origin", "=", "bot"),
                ("create_date", ">=", fields.Datetime.now() - timedelta(hours=1)),
        ]) >= content.BOT_HOURLY_LIMIT:
            raise SendRejected("limite_por_hora",
                               "El bot alcanzo el tope de respuestas por hora.")
        try:
            with mute_logger("odoo.sql_db"), self.env.cr.savepoint():
                message = Message.create({
                    "conversation_id": conversation.id, "direction": "saliente",
                    "origin": origin, "kind": kind, "text": body["texto"] or False,
                    "data": {k: v for k, v in body.items() if k != "texto"},
                    "unique_key": key, "state": "pendiente",
                    "file": base64.b64encode(attachment["content"]) if attachment else False,
                })
        except IntegrityError:
            return Message.search([("unique_key", "=", key)], limit=1), False
        Message._trigger_dispatch()
        return message, True

    def _history(self, limit=10):
        """Últimos mensajes, en orden: la memoria del asistente vive aquí, no en n8n."""
        self.ensure_one()
        messages = self.env["mirabilenet.conversation.message"].sudo().search(
            [("conversation_id", "=", self.id)], order="create_date desc, id desc",
            limit=limit)
        return [{
            "de": "cliente" if m.direction == "entrante"
                  else ("persona" if m.origin == "persona" else "bot"),
            "tipo": m.kind, "texto": (m.text or "")[:500],
        } for m in messages.sorted(lambda m: (m.create_date, m.id))]

    def _handoff(self, reason, message_id, kind=None, notify=True):
        """Abre (o reutiliza) la solicitud, avisa al contacto y pausa el asistente. El aviso
        se encola antes de pausar: después las reglas ya no lo dejarían salir."""
        self.ensure_one()
        conversation = self.sudo()
        if not conversation.partner_id:
            raise SendRejected("no_es_cliente", "Solo se derivan conversaciones de clientes.")
        Case = self.env["mirabilenet.support.case"].sudo()
        self.env.cr.execute(
            "SELECT id FROM mirabilenet_conversation WHERE id = %s FOR UPDATE",
            [conversation.id])
        case = Case.search([("conversation_id", "=", conversation.id),
                            ("state", "in", ("nuevo", "atencion"))], limit=1)
        created = not case
        if created:
            inbound = content.clean_text(message_id, 120) or False
            case = Case.search([("inbound_message_id", "=", inbound)], limit=1) \
                if inbound else Case
            created = not case
            if created:
                case = Case.create({
                    "partner_id": conversation.partner_id.id, "kind": kind or "ayuda",
                    "reason": content.clean_text(reason, 2000) or False,
                    "conversation_id": conversation.id, "inbound_message_id": inbound})
                self.env["mirabilenet.audit.log"]._log(
                    "crear", "Solicitud de atención creada desde una conversación",
                    record=case, region=conversation.partner_id.mirabilenet_region_id,
                    payload={"motivo": case.reason or ""})
            elif not case.conversation_id:
                case.conversation_id = conversation
        if notify and conversation.state == "bot":
            try:
                conversation._enqueue_outgoing(
                    "texto", {"texto": content.HANDOFF_NOTICE}, "derivar:%d" % case.id)
            except SendRejected as exc:
                _logger.info("No se avisó la derivación al contacto: %s", exc.code)
        if conversation.state != "humano":
            conversation.write({"state": "humano"})
        return case, created

    def _return_to_bot(self):
        self.sudo().write({"state": "bot", "attended_by": False})

    # ------------------------------------------------------------------
    # Personas del equipo
    # ------------------------------------------------------------------
    def _require_operator(self):
        if not self.env.su and not self.env.user.has_group(OPERATOR):
            raise AccessError(_("Su rol no atiende conversaciones."))
        self.check_access("read")

    def action_mark_reviewed(self):
        self._require_operator()
        self.sudo().write({"reviewed_at": fields.Datetime.now()})
        return True

    def _reply_as_person(self, text):
        """Respuesta de una persona: pausa el asistente y respeta baja, número y ventana."""
        self.ensure_one()
        self._require_operator()
        conversation = self.sudo()
        # Cada respuesta de una persona es un envío nuevo: la clave no puede depender del
        # reloj, o dos respuestas en el mismo segundo se tomarían por la misma.
        try:
            message, _created = conversation._enqueue_outgoing(
                "texto", {"texto": text},
                "persona:%d:%d:%s" % (conversation.id, self.env.uid, uuid.uuid4().hex),
                origin="persona")
        except SendRejected as exc:
            hint = _(" Fuera de la ventana de 24 horas use una plantilla aprobada.") \
                if exc.code == "fuera_de_ventana" else ""
            raise UserError(exc.detail + hint)
        except ValueError as exc:
            raise UserError(str(exc))
        conversation.write({"state": "humano", "attended_by": self.env.uid,
                            "reviewed_at": fields.Datetime.now()})
        self.env["mirabilenet.audit.log"]._log(
            "crear", "Respuesta de una persona en la conversación con %s"
            % conversation.contact, record=conversation, region=conversation.region_id)
        return message.with_env(self.env)

    def action_return_to_bot(self):
        self._require_operator()
        self._return_to_bot()
        return True

    @api.model
    def _simulate_incoming(self, contact, text):
        """Mensaje de prueba desde el panel: recorre el circuito completo sin salir a Meta.
        No aplica las palabras de baja: con el número de un cliente real lo daría de baja."""
        if not self.env.su and not self.env.user.has_group(OPERATOR):
            raise AccessError(_("Su rol no usa el simulador."))
        try:
            contact = phones.normalize_number(contact)
        except phones.NotSendable as exc:
            raise UserError(str(exc))
        partner = self.env["mirabilenet.whatsapp.message"]._partner_by_number(contact)
        region = partner.sudo().mirabilenet_region_id or self.env.user.mirabilenet_region_id
        if partner and not self.env.su:
            partner.with_env(self.env).check_access("read")
        conversation, message, _created = self._register_incoming(
            "simulador", contact, "texto", text=content.clean_text(text, content.MAX_TEXT),
            external_id="sim-in-%s" % uuid.uuid4().hex, partner=partner, region=region)
        conversation._notify_n8n(message)
        return conversation.with_env(self.env)

    # ------------------------------------------------------------------
    # Webhook de Meta
    # ------------------------------------------------------------------
    @api.model
    def _process_meta_incoming(self, incoming, phone_number_id=""):
        """Un mensaje entrante ya autenticado: baja, comprobante o solicitud; después queda
        en su conversación y se le pasa a n8n. Devuelve lo que resolvió el sistema."""
        handled, proof = self._handle_by_system(incoming)
        contact = str(incoming.get("from") or "")
        external_id = str(incoming.get("id") or "")[:120]
        if not contact or not external_id:
            return handled
        try:
            contact = phones.normalize_number(contact)
        except phones.NotSendable:
            _logger.info("Mensaje entrante con número no válido; no se registra")
            return handled
        kind, text, data = content.normalize_meta_incoming(incoming)
        number = self.env["mirabilenet.whatsapp.number"].sudo().search(
            [("phone_number_id", "=", phone_number_id)], limit=1) if phone_number_id \
            else self.env["mirabilenet.whatsapp.number"]
        try:
            from datetime import datetime
            moment = datetime.utcfromtimestamp(int(incoming.get("timestamp")))
        except (TypeError, ValueError):
            moment = fields.Datetime.now()
        conversation, message, _created = self._register_incoming(
            "whatsapp", contact, kind, text=text, data=data, external_id=external_id,
            number=number, moment=moment)
        if handled == "caso_humano":
            case = self.env["mirabilenet.support.case"].sudo().search(
                [("inbound_message_id", "=", external_id)], limit=1)
            if case:
                conversation._handoff(case.reason, external_id, kind=case.kind)
        conversation._notify_n8n(message, handled, proof)
        return handled

    @api.model
    def _handle_by_system(self, incoming):
        """(manejado, comprobante): «baja», «comprobante», «caso_humano» o nada."""
        original = ((incoming.get("text") or {}).get("body") or "").strip()
        origin = str(incoming.get("from") or "")
        if not origin:
            return None, None
        try:
            contact = phones.normalize_number(origin)
        except phones.NotSendable:
            return None, None
        partner = self.env["mirabilenet.whatsapp.message"]._partner_by_number(contact)
        if not partner:
            return None, None
        if phones.is_opt_out(original):
            self.env["mirabilenet.whatsapp.optout"]._opt_out(
                partner, reason="Respondió «%s»" % original[:150], origin="cliente")
            return "baja", None
        Proof = self.env["mirabilenet.whatsapp.proof"]
        result = Proof._store_from_meta(incoming, partner)
        if result is not None:
            return "comprobante", Proof._for_bot(*result)
        plain = phones.plain_text(original)
        Bot = self.env["mirabilenet.bot.settings"]
        n8n_on = self.env["mirabilenet.n8n.event"]._configured()
        kind = None
        if any(p in plain for p in CANCEL_PHRASES) and not (n8n_on and Bot._load().support_on):
            kind = "baja_servicio"
        elif any(w in plain for w in HELP_WORDS) and not n8n_on:
            kind = "ayuda"
        if not kind:
            return None, None
        Case = self.env["mirabilenet.support.case"].sudo()
        message_id = str(incoming.get("id") or "")[:120] or False
        if not (message_id and Case.search_count([("inbound_message_id", "=", message_id)])):
            case = Case.create({"partner_id": partner.id, "kind": kind,
                                "reason": original[:2000], "inbound_message_id": message_id})
            self.env["mirabilenet.audit.log"]._log(
                "crear", "Solicitud de atención creada desde WhatsApp", record=case,
                region=partner.sudo().mirabilenet_region_id)
        return "caso_humano", None
