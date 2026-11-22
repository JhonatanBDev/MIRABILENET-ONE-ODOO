import hashlib
import logging
import re
import uuid
from datetime import timedelta

from odoo import api, fields, models

from ..whatsapp import money as calc

from ..whatsapp import content, phones
from ..whatsapp.content import SendRejected

_logger = logging.getLogger(__name__)

SERVICE_STATE_LABELS = {
    "pendiente_instalacion": "Pendiente de instalacion", "activo": "Activo",
    "moroso": "Moroso", "suspendido": "Suspendido", "baja": "De baja"}
CONTRACT_STATE_LABELS = {"borrador": "Borrador", "vigente": "Vigente",
                         "suspendido": "Suspendido", "finalizado": "Finalizado"}
PROOF_STATE_LABELS = {"revision": "En verificacion", "verificado": "Verificado",
                      "rechazado": "Rechazado"}


def money(value):
    return "%.2f" % calc.money(value)


class MirabilenetN8nApi(models.AbstractModel):
    """La API que usan los flujos de n8n, con el mismo contrato que tenía el sistema
    anterior: mismas rutas, parámetros, campos de respuesta y códigos de error.

    Cada método devuelve (código HTTP, cuerpo). n8n no ve credenciales ni la base: las
    herramientas reciben el id de la conversación, nunca un teléfono ni un id de cliente,
    así el asistente solo puede consultar al contacto con el que está hablando.
    """
    _name = "mirabilenet.n8n.api"
    _description = "MIRABILENET: API para n8n"

    # -- utilidades -----------------------------------------------------
    @api.model
    def _today(self):
        return self.env["account.move"]._mirabilenet_today()

    @api.model
    def _conversation(self, pk):
        try:
            pk = int(pk)
        except (TypeError, ValueError):
            pk = 0
        return self.env["mirabilenet.conversation"].sudo().browse(pk).exists()

    @api.model
    def _customer_conversation(self, pk):
        conversation = self._conversation(pk)
        if not conversation:
            return None, (404, {"detail": "Conversacion inexistente."})
        if not conversation.partner_id:
            return None, (409, {"codigo": "no_es_cliente",
                                "detail": "El contacto no es un cliente registrado."})
        return conversation, None

    @api.model
    def _prospect_conversation(self, pk):
        conversation = self._conversation(pk)
        if not conversation:
            return None, (404, {"detail": "Conversacion inexistente."})
        if conversation.partner_id:
            return None, (409, {"codigo": "es_cliente",
                                "detail": "El contacto ya es cliente: lo atiende soporte."})
        return conversation, None

    @api.model
    def _partner_by_phone(self, phone):
        try:
            contact = phones.normalize_number(phone)
        except phones.NotSendable:
            return self.env["res.partner"]
        return self.env["mirabilenet.whatsapp.message"]._partner_by_number(contact)

    @api.model
    def _pending(self, partner):
        return self.env["mirabilenet.whatsapp.proof"]._pending_charges(partner)

    @api.model
    def _charge_json(self, charge):
        qr = self.env["mirabilenet.payment.qr"]._current(charge.mirabilenet_region_id)
        partner, service = charge.partner_id, charge.mirabilenet_service_id
        return {
            "id": charge.id, "numero": charge.name,
            "cliente": {"id": partner.id, "nombre": partner.name,
                        "telefono": partner.mirabilenet_whatsapp or partner.phone or ""},
            "servicio": service.id or None,
            "plan": service.plan_id.name or None,
            "region": {"id": charge.mirabilenet_region_id.id, "codigo": charge.mirabilenet_region_id.code,
                       "nombre": charge.mirabilenet_region_id.name},
            "fecha_vencimiento": charge.invoice_date_due.isoformat(),
            "monto_total": money(charge.amount_total), "saldo": money(charge.amount_residual),
            "moneda": charge.currency_id.name, "estado": charge._mirabilenet_charge_state(),
            "qr_url": qr.public_url if qr else None,
        }

    # -- cobranza -------------------------------------------------------
    @api.model
    def charges(self, params):
        """Cargos elegibles; admite ?dias=3 o ?vencidos=true."""
        Charge = self.env["account.move"].sudo()
        today = self._today()
        if str(params.get("vencidos", "")).lower() in ("1", "true", "si"):
            domain = [("invoice_date_due", "<", today)]
        else:
            try:
                days = int(params.get("dias", "3"))
            except (TypeError, ValueError):
                return 400, {"detail": "dias debe ser un entero"}
            if not 0 <= days <= 365:
                return 400, {"detail": "dias fuera de rango"}
            domain = [("invoice_date_due", "=", today + timedelta(days=days))]
        settings = self.env["mirabilenet.whatsapp.settings"]._load()
        Message = self.env["mirabilenet.whatsapp.message"]
        opted_out = self.env["mirabilenet.whatsapp.optout"].sudo().search([]).mapped("partner_id")
        result = []
        for charge in Charge.search(Charge._mirabilenet_open_domain() + domain,
                                    order="invoice_date_due, id"):
            partner = charge.partner_id
            if partner in opted_out:
                continue
            if settings.require_consent and not Message._has_consent(partner):
                continue
            try:
                phones.normalize_number(partner.mirabilenet_whatsapp or partner.phone)
            except phones.NotSendable:
                continue
            result.append(self._charge_json(charge))
        return 200, {"count": len(result), "results": result}

    @api.model
    def customer(self, params):
        """Solo el cliente cuyo WhatsApp coincide exactamente con el origen."""
        partner = self._partner_by_phone(params.get("telefono", ""))
        if not partner:
            return 404, {"detail": "No se pudo validar el numero registrado."}
        payments = self.env["account.payment"].sudo().search(
            [("partner_id", "=", partner.id), ("payment_type", "=", "inbound"),
             ("state", "in", ("in_process", "paid"))], order="date desc, id desc", limit=5)
        services = self.env["mirabilenet.service"].sudo().search(
            [("partner_id", "=", partner.id),
             ("state", "in", ("activo", "moroso", "suspendido"))])
        return 200, {
            "cliente": {"nombre": partner.name, "codigo": partner.mirabilenet_code},
            "servicios": [{"estado": s.state, "plan": s.plan_id.name,
                           "region": s.region_id.name} for s in services],
            "avisos": [self._charge_json(c) for c in self._pending(partner)],
            "pagos_recientes": [{
                "monto": money(p.amount), "moneda": p.currency_id.name,
                "fecha": "%sT00:00:00+00:00" % p.date.isoformat(),
                "metodo": "efectivo" if p.journal_id.type == "cash" else "transferencia"}
                for p in payments],
        }

    @api.model
    def reminders(self, data):
        """Registra un recordatorio por la bandeja, con sus reglas y su idempotencia."""
        Charge = self.env["account.move"].sudo()
        try:
            charge = Charge.browse(int(data.get("aviso_id"))).exists()
        except (TypeError, ValueError):
            charge = Charge
        if not charge:
            return 404, {"detail": "Aviso inexistente."}
        event = data.get("evento", "recordatorio_pago")
        if event not in ("recordatorio_pago", "aviso_vencido", "recordatorio_mora"):
            return 400, {"detail": "Evento no permitido."}
        settings = self.env["mirabilenet.whatsapp.settings"]._load()
        Message = self.env["mirabilenet.whatsapp.message"].sudo()
        today = self._today()
        if event == "recordatorio_pago" and charge.invoice_date_due != today + timedelta(
                days=settings.reminder_days):
            return 409, {"detail": "El aviso no vence dentro del plazo de recordatorio "
                                   "configurado."}
        if event == "aviso_vencido" and charge.invoice_date_due > today:
            return 409, {"detail": "El aviso aun no esta vencido."}
        if event == "recordatorio_mora" and charge.invoice_date_due >= today:
            return 409, {"detail": "El aviso aun no esta vencido."}
        day = str(data.get("clave_dia", today.isoformat()))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            return 400, {"detail": "clave_dia debe tener formato AAAA-MM-DD."}
        extra = day if event == "recordatorio_mora" else ""
        key = "%s:%s%s" % (event, charge.name, (":%s" % extra) if extra else "")
        previous = Message.search([("unique_key", "=", key)], limit=1)
        if previous:
            return 200, {"id": previous.id, "estado": previous.state, "duplicado": True}
        if event == "recordatorio_mora":
            interval = timedelta(days=settings.mora_interval_days)
            earlier = Message.search([("charge_id", "=", charge.id), ("event", "=", event)])
            if len(earlier) >= settings.mora_max_reminders:
                return 409, {"detail": "Se alcanzo el limite de recordatorios de mora."}
            first = Message.search(
                [("charge_id", "=", charge.id), ("event", "=", "aviso_vencido")],
                order="id desc", limit=1)
            reference = (earlier | first).sorted("create_date")[-1:]
            wait = {"detail": "El recordatorio aun no cumple el intervalo configurado."}
            if reference and (reference.state == "pendiente"
                              or reference.create_date > fields.Datetime.now() - interval):
                return 409, wait
            if not reference and charge.invoice_date_due > today - interval:
                return 409, wait
        try:
            message = Message._enqueue(event, charge=charge, extra_key=extra)
        except phones.NotSendable as exc:
            return 400, {"detail": str(exc)}
        if not message:
            return 200, {"encolado": False, "detail": "No elegible, desactivado o ya atendido "
                                                      "por las politicas de WhatsApp."}
        Message._trigger_dispatch()
        return 201, {"id": message.id, "estado": message.state, "duplicado": False}

    @api.model
    def cases(self, data):
        partner = self._partner_by_phone(data.get("telefono", ""))
        if not partner:
            return 404, {"detail": "Numero no asociado a un cliente."}
        kind = data.get("tipo", "ayuda")
        if kind not in ("ayuda", "baja_servicio"):
            return 400, {"detail": "Tipo de solicitud no permitido."}
        message_id = str(data.get("mensaje_id", ""))[:120]
        if not message_id:
            return 400, {"detail": "Falta el identificador del mensaje entrante."}
        Case = self.env["mirabilenet.support.case"].sudo()
        case = Case.search([("inbound_message_id", "=", message_id)], limit=1)
        created = not case
        if created:
            case = Case.create({"partner_id": partner.id, "kind": kind,
                                "reason": str(data.get("motivo", ""))[:2000] or False,
                                "inbound_message_id": message_id})
        return (201 if created else 200), {"id": case.id, "estado": case.state,
                                           "duplicado": not created}

    @api.model
    def opt_outs(self, data):
        partner = self._partner_by_phone(data.get("telefono", ""))
        if not partner:
            return 404, {"detail": "Numero no asociado a un cliente."}
        _optout, created = self.env["mirabilenet.whatsapp.optout"]._opt_out(
            partner, reason="Solicitud por WhatsApp", origin="cliente")
        return 200, {"baja": True, "duplicado": not created}

    @api.model
    def proof_upload(self, data, file_content=None, content_type=""):
        partner = self._partner_by_phone(data.get("telefono", ""))
        if not partner:
            return 404, {"detail": "Numero no asociado a un cliente."}
        try:
            charge_id = int(data.get("aviso_id"))
        except (TypeError, ValueError):
            charge_id = 0
        charge = self._pending(partner).filtered(lambda c: c.id == charge_id)
        if not charge:
            return 400, {"detail": "Seleccione un aviso de cobro valido."}
        if not file_content:
            return 400, {"detail": "Falta el archivo."}
        if content_type not in content.SIGNATURES or len(file_content) > content.MAX_ATTACHMENT:
            return 400, {"detail": "Solo JPG, PNG o PDF de hasta 5 MB."}
        if content.real_type(file_content) != content_type:
            return 400, {"detail": "El contenido no coincide con el tipo de archivo."}
        message_id = str(data.get("mensaje_id", ""))[:120]
        if not message_id:
            return 400, {"detail": "Falta el ID de mensaje de WhatsApp."}
        result, proof = self.env["mirabilenet.whatsapp.proof"]._store(
            partner, file_content, message_id)
        created = result == "guardado"
        if created and proof.charge_id != charge:
            proof.charge_id = charge
        return (201 if created else 200), {"id": proof.id, "estado": proof.state,
                                           "duplicado": not created}

    # -- conversación ---------------------------------------------------
    @api.model
    def conversation(self, pk):
        conversation = self._conversation(pk)
        if not conversation:
            return 404, {"detail": "Conversacion inexistente."}
        from .mirabilenet_conversation import local_iso
        return 200, {
            "id": conversation.id, "canal": conversation.channel,
            "estado": conversation.state, "es_cliente": bool(conversation.partner_id),
            "ventana_abierta": conversation.window_open,
            "ventana_hasta": local_iso(self.env, conversation.window_until),
        }

    @api.model
    def conversation_charges(self, pk):
        conversation, error = self._customer_conversation(pk)
        if error:
            return error
        today = self._today()
        return 200, {"avisos": [{
            "id": c.id, "numero": c.name, "concepto": c._mirabilenet_concept(),
            "saldo": money(c.amount_residual),
            "moneda": c.currency_id.name, "fecha_vencimiento": c.invoice_date_due.isoformat(),
            "vencido": c.invoice_date_due < today,
        } for c in self._pending(conversation.partner_id)[:10]]}

    @api.model
    def conversation_history(self, pk, params):
        conversation = self._conversation(pk)
        if not conversation:
            return 404, {"detail": "Conversacion inexistente."}
        try:
            limit = min(max(int(params.get("limite", "10")), 1), 20)
        except (TypeError, ValueError):
            limit = 10
        return 200, {"mensajes": conversation._history(limit),
                     "estilo": self.env["mirabilenet.bot.settings"]._style_for(conversation)}

    @api.model
    def conversation_proofs(self, pk):
        conversation, error = self._customer_conversation(pk)
        if error:
            return error
        proofs = self.env["mirabilenet.whatsapp.proof"].sudo().search(
            [("partner_id", "=", conversation.partner_id.id)], order="id desc", limit=5)
        Charge = self.env["account.move"]
        tz = self.env["ir.config_parameter"].sudo().get_param(
            "mirabilenet.timezone", "America/La_Paz")
        return 200, {"comprobantes": [{
            "recibido": fields.Datetime.context_timestamp(
                Charge.with_context(tz=tz), p.create_date).strftime("%d/%m/%Y %H:%M"),
            "estado": PROOF_STATE_LABELS[p.state],
            "aviso_numero": p.charge_id.name or None,
            "motivo_rechazo": p.reject_reason or None,
        } for p in proofs]}

    @api.model
    def conversation_service(self, pk):
        conversation, error = self._customer_conversation(pk)
        if error:
            return error
        partner = conversation.partner_id
        services = self.env["mirabilenet.service"].sudo().search(
            [("partner_id", "=", partner.id), ("state", "!=", "baja")])
        contracts = self.env["contract.contract"].sudo().search(
            [("partner_id", "=", partner.id), ("mirabilenet_service_id", "!=", False)],
            order="id desc", limit=3)
        return 200, {
            "titular": partner.name,
            "servicios": [{
                "plan": s.plan_id.name, "bajada_mbps": s.plan_id.mirabilenet_down_mbps,
                "subida_mbps": s.plan_id.mirabilenet_up_mbps,
                "precio_mensual": money(s.monthly_price), "moneda": s.currency_id.name,
                "estado": SERVICE_STATE_LABELS[s.state]} for s in services],
            "contratos": [{"numero": c.code or c.name, "estado": CONTRACT_STATE_LABELS["vigente"],
                           "desde": c.date_start.strftime("%d/%m/%Y")}
                          for c in contracts if c.date_start],
        }

    @api.model
    def conversation_handoff(self, pk, data):
        conversation, error = self._customer_conversation(pk)
        if error:
            return error
        kind = data.get("tipo") or "ayuda"
        if kind not in ("ayuda", "baja_servicio"):
            return 400, {"detail": "Tipo de solicitud no valido."}
        try:
            case, created = conversation._handoff(
                data.get("motivo", ""), "derivar:%s" % data.get("mensaje_id", ""), kind=kind)
        except SendRejected as exc:
            return 409, {"codigo": exc.code, "detail": exc.detail}
        return (201 if created else 200), {"caso_id": case.id, "estado": case.state,
                                           "duplicado": not created}

    @api.model
    def conversation_qr(self, pk, data):
        """Envía al cliente el QR de pago vigente de su región, como imagen. El asistente
        nunca escribe datos bancarios, y recibir el QR no registra nada."""
        import base64
        conversation, error = self._customer_conversation(pk)
        if error:
            return error
        partner = conversation.partner_id
        region = partner.mirabilenet_region_id
        qr = self.env["mirabilenet.payment.qr"]._current(region)
        if not qr or not qr.image:
            self.env["mirabilenet.integration.alert"]._raise(
                "qr-faltante:%d" % region.id, "Bot con IA", "Enviar QR de pago",
                "Un cliente pidió el QR de pago y la región %s no tiene un QR vigente "
                "cargado en Mensajería → QR de pago." % region.name)
            return 409, {"codigo": "sin_qr",
                         "detail": "La región del cliente no tiene un QR de pago vigente."}
        charges = self._pending(partner)[:3]
        lines = ["💳 *QR de pago de MIRABILENET*"]
        if charges:
            lines.append("Tus avisos pendientes:")
            lines += ["• %s: %s %s (vence %s)" % (
                c.name, c.currency_id.name, money(c.amount_residual),
                c.invoice_date_due.strftime("%d/%m/%Y")) for c in charges]
        lines.append("📸 Cuando pagues, envíanos por aquí la foto o el PDF del comprobante y "
                     "lo registramos para verificarlo.")
        raw = base64.b64decode(qr.image)
        mime = content.real_type(raw)
        if mime not in ("image/jpeg", "image/png"):
            _logger.error("QR %s ilegible para la conversación %s", qr.id, conversation.id)
            return 409, {"codigo": "qr_ilegible", "detail": "No se pudo leer la imagen del QR."}
        message_id = str(data.get("mensaje_id") or "")
        try:
            _message, created = conversation._enqueue_outgoing(
                "imagen", {"texto": "\n".join(lines)[:1024]},
                "qr:%d:%s" % (conversation.id, message_id or uuid.uuid4().hex),
                attachment={"content": raw, "mime": mime,
                            "name": content.safe_file_name("qr-pago-%s" % region.code, mime)})
        except SendRejected as exc:
            return 409, {"codigo": exc.code, "detail": exc.detail}
        return (201 if created else 200), {
            "enviado": True, "duplicado": not created, "region": region.name,
            "avisos": [{"numero": c.name, "saldo": money(c.amount_residual),
                        "moneda": c.currency_id.name,
                        "fecha_vencimiento": c.invoice_date_due.strftime("%d/%m/%Y")} for c in charges]}

    @api.model
    def proof_charge(self, pk, proof_pk, data):
        conversation, error = self._customer_conversation(pk)
        if error:
            return error
        try:
            proof_pk = int(proof_pk)
        except (TypeError, ValueError):
            proof_pk = 0
        proof = self.env["mirabilenet.whatsapp.proof"].sudo().search(
            [("id", "=", proof_pk), ("partner_id", "=", conversation.partner_id.id)], limit=1)
        if not proof:
            return 404, {"detail": "Comprobante inexistente para este cliente."}
        try:
            proof = proof._associate(data.get("aviso_id"))
        except ValueError as exc:
            return 409, {"codigo": "no_asociable", "detail": str(exc)}
        charge = proof.charge_id
        return 200, {"comprobante_id": proof.id, "aviso_numero": charge.name,
                     "saldo": money(charge.amount_residual), "moneda": charge.currency_id.name}

    @api.model
    def conversation_retention_offers(self, pk):
        conversation, error = self._customer_conversation(pk)
        if error:
            return error
        promos = self.env["mirabilenet.retention.promo"]._current_for(
            conversation.partner_id.mirabilenet_region_id)[:5]
        return 200, {"promociones": [{
            "nombre": p.name, "oferta": p.offer, "condiciones": p.conditions or "",
            "vigente_hasta": p.date_to.strftime("%d/%m/%Y") if p.date_to else None,
        } for p in promos]}

    @api.model
    def _published_plans(self, domain, order, limit):
        return self.env["product.template"].sudo().search(
            [("mirabilenet_published", "=", True)] + domain, order=order, limit=limit)

    @api.model
    def _plan_currency(self, plan, region=None):
        """La moneda en que se cobra el plan: la de su región; si vale en todas, la de la
        región de quien pregunta. Los cobros van en la moneda de la región, no en la de la
        contabilidad de Odoo."""
        region = plan.mirabilenet_region_id or region or self.env["mirabilenet.region"]
        return (region.currency_id or self.env.ref("base.BOB")).name

    @api.model
    def _plan_json(self, plan, region=None):
        return {"nombre": plan.name, "bajada_mbps": plan.mirabilenet_down_mbps,
                "subida_mbps": plan.mirabilenet_up_mbps,
                "precio_mensual": money(plan.list_price),
                "moneda": self._plan_currency(plan, region),
                "incluye_tv": plan.mirabilenet_includes_tv,
                "region": plan.mirabilenet_region_id.name or "Todas las regiones"}

    @api.model
    def conversation_plans(self, pk):
        """Planes que puede contratar el cliente. El asistente ofrece; el cambio lo hace
        una persona."""
        conversation, error = self._customer_conversation(pk)
        if error:
            return error
        partner = conversation.partner_id
        region = partner.mirabilenet_region_id
        services = self.env["mirabilenet.service"].sudo().search(
            [("partner_id", "=", partner.id), ("state", "!=", "baja")])
        own = services.mapped("plan_id")
        plans = self._published_plans(
            ["|", ("mirabilenet_region_id", "=", region.id),
             ("mirabilenet_region_id", "=", False)], "list_price", 12)
        return 200, {
            "region_del_cliente": region.name or None,
            "tu_plan": [{
                "nombre": s.plan_id.name, "bajada_mbps": s.plan_id.mirabilenet_down_mbps,
                "subida_mbps": s.plan_id.mirabilenet_up_mbps,
                "precio_mensual": money(s.monthly_price),
                "moneda": s.currency_id.name} for s in services],
            "planes_disponibles": [dict(self._plan_json(p, region), es_tu_plan=p in own)
                                   for p in plans],
        }

    @api.model
    def conversation_organization(self, pk):
        """Información pública de la empresa. Quedan fuera los nodos y los datos internos
        de cada región (calendario de cobro, metas)."""
        if not self._conversation(pk):
            return 404, {"detail": "Conversacion inexistente."}
        regions = self.env["mirabilenet.region"].sudo().search([], order="name")
        Branch = self.env["mirabilenet.branch"].sudo()
        Zone = self.env["mirabilenet.zone"].sudo()
        about = (self.env["mirabilenet.bot.settings"]._load().about_us or "").strip()
        return 200, {
            "empresa": self.env.company.name or "MIRABILENET",
            "quienes_somos": about or None,
            "regiones": [{
                "region": r.name,
                "sucursales": [{"nombre": b.name, "direccion": b.address or "",
                                "telefono": b.phone or ""}
                               for b in Branch.search([("region_id", "=", r.id)], order="name")],
                "zonas": [{"zona": z.name, "sector": z.sector or ""}
                          for z in Zone.search([("region_id", "=", r.id)], order="name")],
            } for r in regions],
            "horario_de_atencion": None,
        }

    @api.model
    def _coverage(self):
        """Dónde hay servicio. Una zona activa cuenta como «Cobertura disponible». Si la
        misma localidad está publicada en el sitio web, manda ese dato: es el único que
        puede decir «parcial» o «próximamente»."""
        listing, seen = [], set()
        for region, name, state, detail in (
                self.env["mirabilenet.region"].sudo()._mirabilenet_coverage_localities()):
            seen.add((region.id, name.strip().lower()))
            listing.append({"region": region.name, "zona": name, "sector": "",
                            "estado": state, "detalle": detail})
        zones = self.env["mirabilenet.zone"].sudo().search(
            [("region_id.active", "=", True)])
        listing += [{"region": z.region_id.name, "zona": z.name, "sector": z.sector or "",
                     "estado": "Cobertura disponible", "detalle": ""} for z in zones
                    if (z.region_id.id, z.name.strip().lower()) not in seen]
        listing.sort(key=lambda c: (c["region"], c["zona"]))
        return listing[:150]

    @api.model
    def _conversation_region(self, conversation):
        return conversation.region_id or conversation.number_id.region_id

    @api.model
    def conversation_sales(self, pk):
        conversation, error = self._prospect_conversation(pk)
        if error:
            return error
        region = self._conversation_region(conversation)
        plans = self._published_plans(
            ["|", ("mirabilenet_region_id", "=", False),
             ("mirabilenet_region_id.active", "=", True)], "list_price", 40)
        ordered = plans.sorted(lambda p: (p.mirabilenet_region_id.name or "", p.list_price))
        return 200, {
            "region_del_numero": region.name or None,
            "planes": [{
                "nombre": p.name, "region": p.mirabilenet_region_id.name or "Todas las regiones",
                "bajada_mbps": p.mirabilenet_down_mbps, "subida_mbps": p.mirabilenet_up_mbps,
                "precio_mensual": money(p.list_price),
                "moneda": self._plan_currency(p, region),
                "incluye_tv": p.mirabilenet_includes_tv} for p in ordered],
            "cobertura": self._coverage(),
        }

    @api.model
    def _region_by_locality(self, locality):
        """La región de una localidad, solo si coincide con un dato cargado y sin dudas."""
        text = (locality or "").strip()
        if len(text) < 3:
            return self.env["mirabilenet.region"]
        regions = self.env["mirabilenet.region"].sudo().search([("name", "=ilike", text)])
        for region, name, _state, _detail in (
                self.env["mirabilenet.region"].sudo()._mirabilenet_coverage_localities()):
            if name.strip().lower() == text.lower():
                regions |= region
        regions |= self.env["mirabilenet.zone"].sudo().search(
            ["|", ("name", "=ilike", text), ("sector", "=ilike", text),
             ("region_id.active", "=", True)]).mapped("region_id")
        return regions if len(regions) == 1 else self.env["mirabilenet.region"]

    @api.model
    def conversation_lead(self, pk, data):
        """Registra al interesado como consulta comercial. No crea un cliente: convertir
        una consulta en prospecto es manual."""
        conversation, error = self._prospect_conversation(pk)
        if error:
            return error
        name = content.clean_text(data.get("nombre"), 120)
        if len(name) < 2:
            return 400, {"codigo": "falta_nombre",
                         "detail": "Hace falta el nombre del interesado."}
        simulated = conversation.channel == "simulador"
        origin = "%s:conversacion:%d" % ("simulador" if simulated else "whatsapp",
                                         conversation.id)
        Lead = self.env["crm.lead"].sudo()
        open_lead = Lead.search([("mirabilenet_origin", "=", origin),
                                 ("stage_id.is_won", "=", False)], limit=1)
        if open_lead:
            return 200, {"consulta_id": open_lead.id, "duplicado": True}
        locality = content.clean_text(data.get("localidad"), 120)
        region = self._conversation_region(conversation) or self._region_by_locality(locality)
        lead = Lead.create({
            "name": "Cotización por WhatsApp: %s" % name, "contact_name": name,
            "type": "lead", "phone": conversation.contact[:40], "city": locality or False,
            "mirabilenet_region_id": region.id, "mirabilenet_origin": origin,
            "mirabilenet_plan_interest": content.clean_text(data.get("plan_interes"), 80)
            or False,
            "description": content.clean_text(data.get("mensaje"), 1000) or False,
            "mirabilenet_internal_note": (
                "Creada desde el simulador del panel: es una prueba, no un interesado real."
                if simulated else False),
        })
        self.env["mirabilenet.audit.log"]._log(
            "crear", "Consulta por WhatsApp (bot de ventas) de %s" % name, record=lead,
            region=region, payload={"conversacion_id": conversation.id, "simulado": simulated})
        return 201, {"consulta_id": lead.id, "duplicado": False,
                     "region": region.name or None}

    # -- respuestas, cupo y alertas ------------------------------------
    @api.model
    def messages(self, data):
        """Respuesta del asistente dentro de la ventana de 24 horas. No envía en la
        petición: deja el mensaje en la bitácora y lo despacha una tarea."""
        raw_id = str(data.get("conversacion_id", ""))
        conversation = self._conversation(raw_id) if raw_id.isdigit() else None
        if not conversation:
            return 404, {"detail": "Conversacion inexistente."}
        body = data.get("contenido") or {}
        try:
            message, created = conversation._enqueue_outgoing(
                str(data.get("tipo", "")), body, data.get("clave", ""))
        except ValueError as exc:
            return 400, {"detail": str(exc)}
        except SendRejected as exc:
            return 409, {"codigo": exc.code, "detail": exc.detail}
        model = content.clean_text(body.get("modelo") if isinstance(body, dict) else "", 60)
        if created and model:
            message.write({"data": dict(message.data or {}, modelo=model)})
        return (201 if created else 200), {"id": message.id, "estado": message.state,
                                           "duplicado": not created}

    @api.model
    def ia_exhausted(self, data):
        Bot = self.env["mirabilenet.bot.settings"]
        settings = Bot._load()
        model = content.clean_text(data.get("modelo"), 60)
        if not model or model not in (settings.model, settings.backup_model):
            return 400, {"detail": "Ese modelo no esta configurado."}
        first = Bot._mark_exhausted(model, content.clean_text(data.get("detalle"), 300))
        return (201 if first else 200), {"agotado": model,
                                         "siguiente": Bot._load()._model_to_use() or ""}

    @api.model
    def alerts(self, data):
        workflow = content.clean_text(data.get("workflow"), 150)
        message = content.clean_text(data.get("mensaje"), 1000)
        if not workflow or not message:
            return 400, {"detail": "Faltan workflow y mensaje."}
        node = content.clean_text(data.get("nodo"), 150)
        key = hashlib.sha256(
            ("%s|%s|%s" % (workflow, node, message[:300])).encode()).hexdigest()
        alert, created = self.env["mirabilenet.integration.alert"]._raise(
            key, workflow, node, message, content.clean_text(data.get("ejecucion_id"), 60))
        return (201 if created else 200), {"id": alert.id, "repeticiones": alert.repetitions}
