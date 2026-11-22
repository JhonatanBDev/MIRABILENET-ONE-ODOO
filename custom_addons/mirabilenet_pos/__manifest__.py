{
    "name": "MIRABILENET: Sucursales en el Punto de venta",
    "version": "19.0.1.0.0",
    "summary": "Cada sucursal es un punto de venta; vender un plan es solicitar el servicio",
    "description": "Une el Punto de venta de Odoo con las sucursales y la red. Detalle en "
                   "readme/.",
    "category": "MIRABILENET",
    "author": "MIRABILENET",
    "license": "AGPL-3",
    "depends": ["mirabilenet_isp", "point_of_sale"],
    "data": [
        "security/mirabilenet_pos_security.xml",
        "data/mirabilenet_pos_data.xml",
        "views/pos_config_views.xml",
        "views/pos_order_views.xml",
        "views/mirabilenet_service_views.xml",
        "views/mirabilenet_pos_menus.xml",
    ],
    "application": False,
    "installable": True,
}
