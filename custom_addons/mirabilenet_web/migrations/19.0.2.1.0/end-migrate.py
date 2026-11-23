"""Al final de la actualización (con todos los módulos cargados) los sitios pasan a la
paleta «mirabilenet» con esquinas redondeadas."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["website"]._mirabilenet_apply_theme()
