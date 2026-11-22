import time
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

CUSTOMER_MANAGER = "mirabilenet_isp.group_mirabilenet_customer_manager"
LEAD_KINDS = [("contacto", "Consulta general"), ("cotizacion", "Solicitud de cotización"),
              ("soporte", "Soporte técnico"), ("camaras", "Videovigilancia")]
#: Lo que escribió el visitante. No se edita: es lo que la persona dijo.
VISITOR_FIELDS = {"contact_name", "phone", "email_from", "city", "description",
                  "mirabilenet_plan_interest", "mirabilenet_kind", "mirabilenet_origin",
                  "mirabilenet_web_service_id", "mirabilenet_source_ip",
                  "mirabilenet_user_agent"}
MIN_SECONDS = 3
MAX_SECONDS = 60 * 60 * 6
HOURLY_LIMIT = 5


class CrmLead(models.Model):
    """Consulta recibida desde el sitio o desde el asistente de ventas. No crea un cliente:
    convertirla en prospecto es una decisión de una persona."""
    _inherit = "crm.lead"

    # Los mismos cuatro campos que declara mirabilenet_whatsapp: así ninguno de los dos
    # módulos depende del otro y las consultas de ambos orígenes comparten pantalla.
    mirabilenet_region_id = fields.Many2one("mirabilenet.region", string="Región",
                                            ondelete="set null", index=True)
    mirabilenet_origin = fields.Char(string="Origen de la consulta", index=True, readonly=True)
    mirabilenet_plan_interest = fields.Char(string="Plan de interés")
    mirabilenet_internal_note = fields.Char(string="Nota interna")
    mirabilenet_kind = fields.Selection(LEAD_KINDS, string="Tipo de consulta", readonly=True)
    mirabilenet_status = fields.Selection(
        [("nuevo", "Nuevo"), ("contactado", "Contactado"),
         ("convertido", "Convertido a prospecto"), ("descartado", "Descartado")],
        string="Estado de la consulta", default="nuevo", index=True)
    mirabilenet_web_service_id = fields.Many2one(
        "mirabilenet.web.service", string="Servicio de interés", ondelete="set null",
        readonly=True)
    mirabilenet_customer_id = fields.Many2one("res.partner", string="Prospecto creado",
                                              ondelete="set null", readonly=True)
    mirabilenet_source_ip = fields.Char(string="IP de origen", readonly=True,
                                        groups="base.group_system")
    mirabilenet_user_agent = fields.Char(string="Navegador", readonly=True,
                                         groups="base.group_system")

    def write(self, vals):
        if not self.env.su and VISITOR_FIELDS & set(vals) and any(
                lead.mirabilenet_origin for lead in self.sudo()):
            raise UserError(_(
                "Lo que escribió el visitante no se edita. Use la nota interna."))
        return super().write(vals)

    # ------------------------------------------------------------------
    @api.model
    def _mirabilenet_validate_web_form(self, data, now=None):
        """Valida el formulario público. Devuelve (valores limpios, errores por campo)."""
        errors = {}

        def fail(name, message):
            errors.setdefault(name, []).append(message)

        values = {k: (data.get(k) or "").strip() for k in (
            "tipo", "nombre", "telefono", "email", "localidad", "region", "servicio",
            "plan_interes", "mensaje", "origen", "ts")}
        if values["tipo"] not in dict(LEAD_KINDS):
            values["tipo"] = "contacto"
        if data.get("website"):
            fail("general", "No se pudo procesar el envio.")
        try:
            elapsed = (now or time.time()) - float(values["ts"])
        except (TypeError, ValueError):
            elapsed = None
        if elapsed is None:
            fail("ts", "No se pudo procesar el envio.")
        elif elapsed < MIN_SECONDS:
            fail("ts", "El formulario se envio demasiado rapido. Intente nuevamente.")
        elif elapsed > MAX_SECONDS:
            fail("ts", "El formulario expiro. Vuelva a cargarlo e intente de nuevo.")
        if len(values["nombre"]) < 3:
            fail("nombre", "Ingrese su nombre completo.")
        elif "http://" in values["nombre"].lower() or "https://" in values["nombre"].lower():
            fail("nombre", "El nombre no puede contener enlaces.")
        if sum(c.isdigit() for c in values["telefono"]) < 7:
            fail("telefono", "Ingrese un telefono valido.")
        if values["email"] and ("@" not in values["email"] or " " in values["email"]):
            fail("email", "Ingrese un correo valido.")
        if values["mensaje"].lower().count("http") > 2:
            fail("mensaje", "El mensaje contiene demasiados enlaces.")
        if not data.get("acepta"):
            fail("acepta", "Debe autorizar el uso de sus datos para responderle.")
        values["acepta"] = bool(data.get("acepta"))
        return values, errors

    @api.model
    def _mirabilenet_too_many(self, ip):
        """Varias consultas desde la misma conexión en una hora: se frena el envío."""
        if not ip:
            return False
        since = fields.Datetime.now() - timedelta(hours=1)
        return self.sudo().search_count([
            ("mirabilenet_source_ip", "=", ip), ("create_date", ">=", since)]) >= HOURLY_LIMIT

    @api.model
    def _mirabilenet_create_from_web(self, values, ip="", user_agent=""):
        Region = self.env["mirabilenet.region"].sudo()
        Service = self.env["mirabilenet.web.service"].sudo()
        region = Region.browse(int(values["region"])).exists() \
            if values["region"].isdigit() else Region
        service = Service.browse(int(values["servicio"])).exists() \
            if values["servicio"].isdigit() else Service
        kind = dict(LEAD_KINDS)[values["tipo"]]
        lead = self.sudo().create({
            "name": "%s: %s" % (kind, values["nombre"]), "type": "lead",
            "contact_name": values["nombre"][:120], "phone": values["telefono"][:40],
            "email_from": values["email"][:254] or False,
            "city": values["localidad"][:120] or False,
            "description": values["mensaje"][:2000] or False,
            "mirabilenet_kind": values["tipo"], "mirabilenet_region_id": region.id,
            "mirabilenet_web_service_id": service.id,
            "mirabilenet_plan_interest": values["plan_interes"][:80] or False,
            "mirabilenet_origin": "web:%s" % (values["origen"][:190] or "/"),
            "mirabilenet_source_ip": ip or False,
            "mirabilenet_user_agent": (user_agent or "")[:255] or False,
        })
        self.env["mirabilenet.audit.log"]._log(
            "crear", "Consulta web de %s (%s)" % (values["nombre"], kind), record=lead,
            region=region, payload={"tipo": values["tipo"], "servicio": service.name or ""})
        return lead

    # ------------------------------------------------------------------
    def _mirabilenet_require_manager(self):
        if not self.env.su and not self.env.user.has_group(CUSTOMER_MANAGER):
            raise AccessError(_("Su rol no gestiona consultas."))
        self.check_access("write")

    def action_mirabilenet_contacted(self):
        self._mirabilenet_require_manager()
        self.filtered(lambda l: l.mirabilenet_status == "nuevo").write(
            {"mirabilenet_status": "contactado"})
        return True

    def action_mirabilenet_discard(self):
        self._mirabilenet_require_manager()
        self.filtered(lambda l: l.mirabilenet_status != "convertido").write(
            {"mirabilenet_status": "descartado"})
        return True

    def action_mirabilenet_to_prospect(self):
        """Crea el cliente en estado Prospecto y lo enlaza. Es una acción de una persona."""
        self.ensure_one()
        self._mirabilenet_require_manager()
        lead = self.sudo()
        if lead.mirabilenet_customer_id:
            return lead.mirabilenet_customer_id.with_env(self.env)
        region = lead.mirabilenet_region_id or self.env.user.mirabilenet_region_id
        if not region:
            raise UserError(_("Indique la región de la consulta antes de convertirla."))
        kind = dict(LEAD_KINDS).get(lead.mirabilenet_kind) or _("consulta")
        partner = self.env["res.partner"].create({
            "name": lead.contact_name or lead.name, "mirabilenet_is_customer": True,
            "mirabilenet_region_id": region.id, "phone": lead.phone,
            "mirabilenet_whatsapp": lead.phone, "email": lead.email_from,
            "street": lead.city, "user_id": self.env.uid,
            "comment": ("Origen: %s (%s).\n%s" % (
                "web" if (lead.mirabilenet_origin or "").startswith("web:") else "WhatsApp",
                kind, lead.description or "")).strip(),
        })
        lead.write({"mirabilenet_customer_id": partner.id, "mirabilenet_status": "convertido",
                    "mirabilenet_region_id": region.id})
        self.env["mirabilenet.audit.log"]._log(
            "crear", "Prospecto %s creado desde una consulta" % partner.mirabilenet_code,
            record=partner, region=region, payload={"consulta": lead.id})
        return partner

    def action_mirabilenet_convert(self):
        partner = self.action_mirabilenet_to_prospect()
        return {"type": "ir.actions.act_window", "res_model": "res.partner",
                "res_id": partner.id, "view_mode": "form", "target": "current"}
