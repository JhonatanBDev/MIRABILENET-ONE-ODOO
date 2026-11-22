from odoo import api, fields, models

from ..whatsapp import n8n

MAX_EVENT_ATTEMPTS = 4


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
    def _cron_deliver(self):
        pending = self.sudo().search([("state", "=", "pendiente")], limit=200)
        pending._deliver()
        return len(pending)
