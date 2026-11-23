from odoo import _, api, fields, models

from ..whatsapp import n8n

MAX_EVENT_ATTEMPTS = 4
#: Segundos que se espera a que la persona termine de escribir antes de pasarle sus mensajes
#: al asistente (se juntan en uno). Se cambia con este parámetro; 0 lo apaga.
BURST_PARAM = "mirabilenet.n8n_agrupar_segundos"
BURST_DEFAULT = 8


class MirabilenetN8nEvent(models.Model):
    """Eventos por entregar a n8n. Solo viajan los que Odoo ya autenticó y registró."""
    _name = "mirabilenet.n8n.event"
    _description = "MIRABILENET: evento hacia n8n"
    _order = "id"

    payload = fields.Json(string="Evento", required=True, readonly=True)
    state = fields.Selection(
        [("pendiente", "Pendiente"), ("enviado", "Entregado"), ("fallido", "Fallido")],
        string="Estado", default="pendiente", required=True, index=True, readonly=True)
    attempts = fields.Integer(string="Intentos", readonly=True)
    error_detail = fields.Char(string="Detalle del error", readonly=True)

    @api.model
    def _url(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "mirabilenet.n8n_inbound_webhook_url") or ""

    @api.model
    def _configured(self):
        return bool(self._url() and n8n.webhook_secret())

    @api.model
    def _client(self):
        mode = self.env["ir.config_parameter"].sudo().get_param("mirabilenet.n8n_client", "real")
        return n8n.FakeN8NClient() if mode == "fake" else n8n.RealN8NClient()

    @api.model
    def _enqueue(self, payload):
        event = self.sudo().create({"payload": payload})
        self.env.ref("mirabilenet_whatsapp.cron_deliver_n8n_events").sudo()._trigger()
        return event

    def _deliver(self):
        hosts = tuple(h.strip() for h in (self.env["ir.config_parameter"].sudo().get_param(
            "mirabilenet.n8n_internal_hosts") or ",".join(n8n.DEFAULT_INTERNAL_HOSTS)
        ).split(",") if h.strip())
        client, url, secret = self._client(), self._url(), n8n.webhook_secret()
        for event in self.sudo().filtered(lambda e: e.state == "pendiente"):
            attempts = event.attempts + 1
            try:
                if not (url and secret):
                    raise n8n.N8NError("reenvío a n8n sin configurar")
                client.post(url, event.payload, secret, hosts)
            except n8n.N8NError as exc:
                final = attempts >= MAX_EVENT_ATTEMPTS
                event.write({"attempts": attempts, "error_detail": str(exc)[:255],
                             "state": "fallido" if final else "pendiente"})
                if final:
                    # Si n8n no responde, el contacto se queda sin respuesta: que no pase
                    # en silencio.
                    self.env["mirabilenet.integration.alert"]._raise(
                        "reenvio-n8n:%s" % str(exc)[:80],
                        "Odoo → n8n (reenvío de mensajes)", "",
                        "No se pudo entregar a n8n el mensaje %s después de varios intentos "
                        "(%s). El contacto no recibió respuesta del asistente." % (
                            (event.payload or {}).get("mensaje_id", "?"), exc))
                continue
            event.write({"attempts": attempts, "state": "enviado", "error_detail": False})
        return True

    @api.model
    def _burst_seconds(self):
        """Cuánto se espera a que la persona termine de escribir. 0 = no esperar."""
        try:
            return max(0, int(self.env["ir.config_parameter"].sudo().get_param(
                BURST_PARAM, str(BURST_DEFAULT))))
        except (TypeError, ValueError):
            return BURST_DEFAULT

    def _group_bursts(self):
        """Junta los mensajes de texto seguidos de una misma conversación en uno solo.

        La gente escribe «hola», después la pregunta y después el detalle, en mensajes
        separados. Si cada uno va solo al asistente, contesta al «hola» sin haber leído lo
        demás. Aquí se espera unos segundos desde el último mensaje y se entrega uno solo,
        con los textos unidos por saltos de línea. Devuelve los eventos listos para salir."""
        wait = self._burst_seconds()
        if not wait:
            return self
        now = fields.Datetime.now()
        ready = self.browse()
        groups = {}
        for event in self.sorted("id"):
            payload = event.payload or {}
            conversation = (payload.get("conversacion") or {}).get("id")
            if payload.get("evento") != "mensaje_entrante" or not conversation:
                ready |= event
                continue
            groups.setdefault(conversation, self.browse())
            groups[conversation] |= event
        retry_at = None
        for events in groups.values():
            newest = max(events.mapped("create_date"))
            due = fields.Datetime.add(newest, seconds=wait)
            if due > now and not any(events.mapped("attempts")):
                retry_at = min(retry_at, due) if retry_at else due
                continue
            texts = events.filtered(lambda e: self._is_plain_text(e.payload))
            if len(texts) > 1:
                last = texts[-1]
                payload = dict(last.payload)
                message = dict(payload.get("mensaje") or {})
                message["texto"] = "\n".join(
                    (e.payload["mensaje"].get("texto") or "").strip() for e in texts)[:4000]
                payload["mensaje"] = message
                payload["mensajes_agrupados"] = [e.payload.get("mensaje_id") for e in texts]
                last.payload = payload
                (texts - last).write({"state": "enviado", "error_detail": _(
                    "Agrupado con el mensaje %s.", payload.get("mensaje_id"))[:255]})
                events -= texts - last
            ready |= events
        if retry_at:
            self.env.ref("mirabilenet_whatsapp.cron_deliver_n8n_events").sudo()._trigger(
                at=retry_at)
        return ready

    @api.model
    def _is_plain_text(self, payload):
        """Un mensaje de texto común: sin botón, sin adjunto y sin que el sistema lo haya
        resuelto ya (una baja, un comprobante)."""
        message = (payload or {}).get("mensaje") or {}
        return (message.get("tipo") == "texto" and not message.get("opcion_id")
                and not payload.get("manejado_por_sistema") and not payload.get("comprobante"))

    @api.model
    def _cron_deliver(self):
        pending = self.sudo().search([("state", "=", "pendiente")], limit=200)
        ready = pending._group_bursts()
        ready._deliver()
        return len(ready)
