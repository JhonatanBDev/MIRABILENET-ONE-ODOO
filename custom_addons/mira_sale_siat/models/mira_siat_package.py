import uuid

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..siat import constants, errors as siat_errors
from ..siat.packaging import sha256_hex, tar_gz

from .mira_siat_event import SUPERVISOR


class MiraSiatPackage(models.Model):
    _name = "mira.siat.package"
    _description = "Mira_Sale SIAT: paquete de facturas"
    _order = "event_id, number"

    name = fields.Char(string="Paquete", compute="_compute_name", store=True)
    event_id = fields.Many2one("mira.siat.event", string="Evento", required=True,
                               ondelete="restrict", index=True)
    company_id = fields.Many2one(related="event_id.company_id", store=True, index=True)
    pos_id = fields.Many2one(related="event_id.pos_id", store=True)
    number = fields.Integer(string="N.º de paquete", required=True, readonly=True)
    invoice_ids = fields.One2many("mira.siat.invoice", "package_id", string="Facturas")
    invoice_count = fields.Integer(string="Cantidad de facturas", readonly=True)
    attachment_id = fields.Many2one("ir.attachment", string="Archivo", readonly=True)
    file_hash = fields.Char(string="Hash del paquete", readonly=True)
    reception_code = fields.Char(string="Código de recepción", readonly=True)
    state = fields.Selection(
        [("draft", "Por enviar"), ("sent", "Enviado"), ("validated", "Validado"),
         ("observed", "Observado")],
        string="Estado", default="draft", required=True, readonly=True, index=True)
    siat_messages = fields.Text(string="Mensajes del SIN", readonly=True)
    correlation_id = fields.Char(readonly=True)

    @api.depends("event_id", "number")
    def _compute_name(self):
        for package in self:
            package.name = "%s / paquete %s" % (package.event_id.name, package.number)

    def unlink(self):
        raise UserError(_("Los paquetes fiscales no se eliminan."))

    @api.model
    def _build(self, event, number, invoices):
        files = [("%s.xml" % inv.cuf, inv._xml_bytes()) for inv in invoices]
        data = tar_gz(files)
        package = self.sudo().create({
            "event_id": event.id,
            "number": number,
            "invoice_count": len(invoices),
            "file_hash": sha256_hex(data),
            "correlation_id": str(uuid.uuid4()),
        })
        attachment = self.env["ir.attachment"].sudo().create({
            "name": "paquete-%s-%s.tar.gz" % (event.id, number),
            "raw": data,
            "mimetype": "application/gzip",
            "res_model": self._name,
            "res_id": package.id,
        })
        package.attachment_id = attachment.id
        invoices._set(state="packaged", package_id=package.id)
        return package

    def _args(self):
        pos = self.pos_id
        gateway = self.company_id._mira_siat_gateway(self.correlation_id)
        return gateway, pos._siat_context(), pos._get_cuis()._code(), pos._get_cufd()._code()

    def _send(self):
        self.ensure_one()
        service = self.env["mira.siat.service"]
        package = self.sudo()
        invoices = package.invoice_ids
        try:
            gateway, ctx, cuis, cufd = package._args()
            result = gateway.send_package(
                ctx, cuis, cufd, invoices[:1].sector_code, invoices[:1].invoice_type,
                package.attachment_id.raw, package.file_hash,
                service._fiscal_iso(service._fiscal_now()),
                package.event_id.reception_code, package.invoice_count,
                cafc=package.event_id.cafc_id.name or None)
        except siat_errors.SiatError as exc:
            # Queda "por enviar": se reintenta con el mismo archivo.
            package.pos_id._mark_comm_error()
            package.siat_messages = "[%s] %s" % (exc.code, exc.message)
            return False
        if not result.ok or not result.reception_code:
            package.write({"state": "observed", "siat_messages": result.messages_text()})
            service._audit("package.rejected", package,
                           correlation_id=package.correlation_id)
            return False
        package.write({"state": "sent", "reception_code": result.reception_code,
                       "siat_messages": False})
        invoices._set(state="package_sent")
        service._audit("package.sent", package, after={"reception": result.reception_code},
                       correlation_id=package.correlation_id)
        return True

    def _validate(self):
        self.ensure_one()
        service = self.env["mira.siat.service"]
        package = self.sudo()
        invoices = package.invoice_ids
        try:
            gateway, ctx, cuis, cufd = package._args()
            result = gateway.validate_package(
                ctx, cuis, cufd, invoices[:1].sector_code, invoices[:1].invoice_type,
                package.reception_code)
        except siat_errors.SiatError as exc:
            package.pos_id._mark_comm_error()
            package.siat_messages = "[%s] %s" % (exc.code, exc.message)
            return False
        if result.ok and result.status_code == constants.ST_PENDING:
            return False
        if result.ok and result.status_code in constants.ACCEPTED_STATES:
            package.write({"state": "validated", "siat_messages": False})
            invoices._set(state="package_validated", error_code=False,
                          reception_code=package.reception_code)
            service._audit("package.validated", package,
                           correlation_id=package.correlation_id)
            return True
        package.write({"state": "observed", "siat_messages": result.messages_text()})
        service._audit("package.observed", package, correlation_id=package.correlation_id)
        return False

    def action_reconcile(self):
        """Paquete observado: concilia factura por factura contra el SIN y deja
        marcadas las rechazadas."""
        service = self.env["mira.siat.service"]
        service._require_group(SUPERVISOR, "package.reconcile")
        for package in self.sudo():
            for invoice in package.invoice_ids.filtered(
                    lambda i: i.state in ("packaged", "package_sent")):
                try:
                    gateway, ctx, cuis, cufd = invoice._gateway_args()
                    status = gateway.check_invoice_status(
                        ctx, cuis, cufd, invoice.sector_code, int(invoice.emission_type),
                        invoice.invoice_type, invoice.cuf)
                except siat_errors.SiatError as exc:
                    raise service._user_error(exc)
                if status.ok and status.status_code in constants.ACCEPTED_STATES:
                    invoice._set(state="package_validated", error_code=False,
                                 siat_status_code=status.status_code)
                else:
                    invoice._set(state="rejected", error_code=siat_errors.REJECTED,
                                 siat_status_code=status.status_code,
                                 siat_messages=status.messages_text())
            package.event_id._check_done()
        return True
