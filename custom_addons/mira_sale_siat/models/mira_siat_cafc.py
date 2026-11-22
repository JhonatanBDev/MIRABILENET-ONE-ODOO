from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MiraSiatCafc(models.Model):
    """Talonario de facturas manuales autorizado por el SIN (CAFC)."""
    _name = "mira.siat.cafc"
    _description = "Mira_Sale SIAT: talonario CAFC"
    _order = "pos_id, number_from"

    name = fields.Char(string="Código CAFC", required=True, size=50)
    pos_id = fields.Many2one("mira.siat.pos", string="Punto de venta", required=True,
                             ondelete="restrict", index=True)
    company_id = fields.Many2one(related="pos_id.company_id", store=True, index=True)
    number_from = fields.Integer(string="Desde el n.º", required=True)
    number_to = fields.Integer(string="Hasta el n.º", required=True)
    date_due = fields.Date(string="Vence el")
    note = fields.Text(string="Notas")
    active = fields.Boolean(default=True)
    invoice_ids = fields.One2many("mira.siat.invoice", "cafc_id", string="Facturas transcritas")
    used_count = fields.Integer(string="Usadas", compute="_compute_usage")
    available_count = fields.Integer(string="Disponibles", compute="_compute_usage")

    _name_company_uniq = models.Constraint(
        "unique(name, company_id)", "Ese código CAFC ya existe en la empresa.")
    _range_check = models.Constraint(
        "CHECK(number_from > 0 AND number_to >= number_from)",
        "El rango del talonario no es válido.")

    @api.depends("invoice_ids.state", "number_from", "number_to")
    def _compute_usage(self):
        for cafc in self:
            used = len(cafc.invoice_ids.filtered(lambda i: i.state != "rejected"))
            cafc.used_count = used
            cafc.available_count = max(cafc.number_to - cafc.number_from + 1 - used, 0)

    def _check_number(self, number, when):
        """El número del papel debe ser del talonario, estar libre y el
        talonario no debe haber vencido en la fecha de la factura."""
        self.ensure_one()
        if not self.number_from <= (number or 0) <= self.number_to:
            raise UserError(_(
                "El número %(number)s está fuera del talonario %(cafc)s "
                "(%(start)s a %(end)s).",
                number=number, cafc=self.name, start=self.number_from, end=self.number_to))
        if self.date_due and when.date() > self.date_due:
            raise UserError(_(
                "El talonario %(cafc)s venció el %(date)s.", cafc=self.name,
                date=self.date_due))
        if self.invoice_ids.filtered(lambda i: i.number == number and i.state != "rejected"):
            raise UserError(_(
                "El número %(number)s del talonario %(cafc)s ya fue transcrito.",
                number=number, cafc=self.name))
        return True
