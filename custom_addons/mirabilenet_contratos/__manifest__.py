{
    "name": "MIRABILENET: Cobros sobre contratos y facturas",
    "version": "19.0.1.1.0",
    "summary": "Une el servicio de red con el contrato recurrente (OCA) y la factura de Odoo",
    "description": "Cada servicio se cobra con un contrato recurrente que emite facturas de "
                   "Odoo; el corte y la reactivación leen esas facturas. Detalle en readme/.",
    "category": "MIRABILENET",
    "author": "MIRABILENET",
    "license": "AGPL-3",
    "depends": ["mirabilenet_isp", "account", "contract", "contract_variable_qty_prorated"],
    "data": [
        "security/mirabilenet_contratos_security.xml",
        "data/mirabilenet_contratos_data.xml",
        "views/mirabilenet_service_views.xml",
        "views/account_move_views.xml",
        "views/contract_contract_views.xml",
        "views/mirabilenet_contratos_menus.xml",
    ],
    "application": False,
    "installable": True,
}
