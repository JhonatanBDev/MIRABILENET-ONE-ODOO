from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from ..siat import constants, errors as siat_errors

# Contactos de casos especiales que instala el módulo.
RESERVED_XMLIDS = (
    "mira_sale_siat.partner_nit_99001",
    "mira_sale_siat.partner_nit_99002",
    "mira_sale_siat.partner_nit_99003",
)


class ResPartner(models.Model):
    _inherit = "res.partner"

    mira_siat_doc_type_id = fields.Many2one(
        "mira.siat.catalog.item", string="Tipo de documento (SIAT)",
        company_dependent=True,
        domain=lambda self: [("catalog_type", "=", "tipo_documento_identidad"),
                             ("company_id", "=", self.env.company.id)])
    mira_siat_complement = fields.Char(string="Complemento", size=5)
    mira_siat_legal_name = fields.Char(
        string="Razón social fiscal",
        help="Nombre que sale en la factura. Si se deja vacío se usa el nombre del contacto.")
    mira_siat_is_reserved_nit = fields.Boolean(compute="_compute_mira_siat_is_reserved_nit")

    @api.depends("vat")
    def _compute_mira_siat_is_reserved_nit(self):
        for partner in self:
            partner.mira_siat_is_reserved_nit = (
                (partner.vat or "").strip() in constants.RESERVED_NITS)

    def _mira_siat_doc_code(self, company=None):
        self.ensure_one()
        item = self.with_company(company or self.env.company).mira_siat_doc_type_id
        return int(item.code) if item and item.code.isdigit() else 0

    @api.constrains("vat", "mira_siat_doc_type_id")
    def _check_mira_siat_numeric_document(self):
        for partner in self:
            number = (partner.vat or "").strip()
            if number and partner._mira_siat_doc_code() in constants.NUMERIC_DOC_TYPES \
                    and not number.isdigit():
                raise ValidationError(_(
                    "El NIT y el CI solo admiten dígitos (%(name)s: «%(number)s»). Si el "
                    "documento tiene letras, cambie el tipo de documento SIAT a "
                    "pasaporte, cédula de extranjero u otro documento.",
                    name=partner.display_name, number=number))

    def _mira_siat_reserved_template(self):
        return self.env.ref("mira_sale_siat.partner_nit_99001", raise_if_not_found=False)

    def _mira_siat_fiscal_identity(self, company):
        """Datos del comprador para el documento fiscal, ya validados."""
        self.ensure_one()
        number = (self.vat or "").strip()
        name = (self.mira_siat_legal_name or self.name or "").strip()
        if not number:
            raise UserError(_(
                "Nominatividad: el cliente «%s» no tiene número de documento. Toda "
                "factura identifica al comprador; para ventas menores sin datos use "
                "el contacto de NIT 99003.", self.display_name))
        if number in constants.RESERVED_NITS:
            if number == constants.NIT_FOREIGNER and self == self._mira_siat_reserved_template():
                raise UserError(_(
                    "El contacto 99001 es una plantilla. Duplíquelo y ponga la razón "
                    "social del cliente extranjero; el NIT 99001 puede repetirse."))
            return {
                "name": constants.RESERVED_NITS[number] or name,
                "doc_type": constants.DOC_TYPE_NIT,
                "number": number,
                "complement": None,
            }
        doc_code = self._mira_siat_doc_code(company)
        if not doc_code:
            raise UserError(_(
                "Indique el tipo de documento SIAT del cliente «%s».", self.display_name))
        if not name:
            raise UserError(_("El cliente no tiene nombre o razón social."))
        if doc_code in constants.NUMERIC_DOC_TYPES and not number.isdigit():
            raise UserError(_(
                "El NIT y el CI solo admiten dígitos: «%s».", number))
        return {
            "name": name,
            "doc_type": doc_code,
            "number": number,
            "complement": (self.mira_siat_complement or None)
            if doc_code == constants.DOC_TYPE_CI else None,
        }

    def unlink(self):
        if not self.env.context.get("_force_unlink"):
            reserved = self.env["res.partner"]
            for xmlid in RESERVED_XMLIDS:
                reserved |= self.env.ref(xmlid, raise_if_not_found=False) or reserved
            if self & reserved:
                raise UserError(_(
                    "Los contactos de NIT 99001, 99002 y 99003 son casos especiales "
                    "de la normativa. No se eliminan; puede archivarlos."))
        return super().unlink()

    def action_mira_siat_verify_nit(self):
        """Consulta al SIN si el NIT del contacto está activo (informativo)."""
        self.ensure_one()
        number = (self.vat or "").strip()
        if not number.isdigit():
            raise UserError(_("El NIT debe ser numérico para poder consultarlo."))
        if number in constants.RESERVED_NITS:
            message, kind = _("NIT reservado para casos especiales: no se consulta al SIN."), "info"
        else:
            pos = self.env.company._mira_siat_default_pos() or self.env["mira.siat.pos"].search(
                [("company_id", "=", self.env.company.id), ("code", ">=", 0)], limit=1)
            if not pos:
                raise UserError(_("Configure primero un punto de venta SIAT."))
            service = self.env["mira.siat.service"]
            try:
                result = pos._verify_nit(number)
            except siat_errors.SiatError as exc:
                raise service._user_error(exc)
            if result.ok:
                message, kind = _("NIT ACTIVO según el SIN."), "success"
            else:
                message = _("El SIN no reporta el NIT como activo: %s",
                            result.messages_text() or "-")
                kind = "warning"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Verificación de NIT %s", number), "message": message,
                       "type": kind, "sticky": kind == "warning"},
        }
