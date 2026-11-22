from odoo import api, fields, models


class MiraSiatSequence(models.Model):
    """Numeración fiscal por empresa + sucursal + punto de venta + sector."""
    _name = "mira.siat.sequence"
    _description = "Mira_Sale SIAT: secuencia de facturas"

    pos_id = fields.Many2one("mira.siat.pos", string="Punto de venta", required=True,
                             ondelete="restrict", index=True)
    company_id = fields.Many2one(related="pos_id.company_id", store=True, index=True)
    sector_code = fields.Integer(string="Documento sector", required=True)
    next_number = fields.Integer(string="Próximo número", required=True, default=1)

    _pos_sector_uniq = models.Constraint(
        "unique(pos_id, sector_code)",
        "Ya existe una secuencia para ese punto de venta y sector.")

    @api.model
    def _reserve(self, pos, sector_code):
        """Reserva el siguiente número de forma atómica (bloqueo de fila)."""
        sequence = self.sudo().search(
            [("pos_id", "=", pos.id), ("sector_code", "=", sector_code)], limit=1)
        if not sequence:
            sequence = self.sudo().create({"pos_id": pos.id, "sector_code": sector_code})
        sequence.flush_recordset()
        self.env.cr.execute(
            "UPDATE mira_siat_sequence SET next_number = next_number + 1 "
            "WHERE id = %s RETURNING next_number - 1", [sequence.id])
        number = self.env.cr.fetchone()[0]
        sequence.invalidate_recordset(["next_number"])
        return number
