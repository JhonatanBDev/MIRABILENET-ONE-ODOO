{
    "name": "MIRABILENET: Factura fiscal al cobrar",
    "version": "19.0.1.0.0",
    "summary": "Emite la factura SIAT cuando la factura del servicio queda pagada",
    "description": "Puente entre mirabilenet_contratos y mira_sale_siat. Un fallo del SIN no "
                   "deshace el pago: queda pendiente y se reintenta. Detalle en readme/.",
    "category": "MIRABILENET",
    "author": "MIRABILENET",
    "license": "AGPL-3",
    "depends": ["mirabilenet_contratos", "mira_sale_siat"],
    "data": [
        "data/mirabilenet_contratos_siat_data.xml",
        "views/res_company_views.xml",
        "views/account_move_views.xml",
    ],
    "auto_install": True,
    "installable": True,
}
