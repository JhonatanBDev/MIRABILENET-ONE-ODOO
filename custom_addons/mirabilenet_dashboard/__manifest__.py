{
    "name": "MIRABILENET: Dashboard",
    "version": "19.0.1.0.0",
    "summary": "Una pantalla con todo el sistema: clientes, cobros, cartera, red, capacidad y soporte",
    "description": "Dashboard dinámico que se actualiza solo, filtrado por periodo y región, con "
                   "gráficos y cada número enlazado a su lista. Es la pantalla de inicio. "
                   "Detalle en readme/.",
    "category": "MIRABILENET",
    "author": "MIRABILENET",
    "license": "AGPL-3",
    "depends": [
        "mirabilenet_indicadores",
        "mirabilenet_pos",
        "mirabilenet_fibra",
        "mirabilenet_web",
        "maintenance",
    ],
    "data": [
        "views/mirabilenet_dashboard_views.xml",
        # Después de la acción: el valor por defecto la nombra.
        "data/ir_default_data.xml",
        "views/mirabilenet_dashboard_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mirabilenet_dashboard/static/src/dashboard/*",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "application": False,
    "installable": True,
}
