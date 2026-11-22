"""Las cajas NAP que todavía no tenían puertos pasan al estándar (8 si no se cambió)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["mirabilenet.fiber.nap"]._mirabilenet_apply_standard_ports()
