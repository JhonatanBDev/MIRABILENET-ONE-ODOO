"""SIAT Adapter: capa independiente del ORM.

Nada de este paquete importa Odoo. El dominio lo usa a través de `gateway`.
"""

from . import amounts, constants, cuf, errors, gateway, packaging, vault, xml_builder, xsd_validator
