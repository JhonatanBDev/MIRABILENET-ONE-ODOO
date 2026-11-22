{
    "name": "MIRABILENET: Red de fibra",
    "version": "19.0.1.2.0",
    "summary": "Cajas NAP, puertos, tramos y clientes sobre un mapa interactivo",
    "description": "Cajas NAP con sus puertos asignados a servicios, tramos de fibra con su "
                   "recorrido, importación de los CSV del relevamiento y de KML/KMZ de Google "
                   "Earth, averías con el módulo de mantenimiento y un mapa con Leaflet. "
                   "Aislado por región. Detalle en readme/.",
    "category": "MIRABILENET",
    "author": "MIRABILENET",
    "license": "AGPL-3",
    "depends": [
        "mirabilenet_isp",
        "mail",
        "contacts",
        "base_geolocalize",
        "maintenance",
        "web_leaflet_lib",
    ],
    "data": [
        "security/mirabilenet_fibra_security.xml",
        "security/ir.model.access.csv",
        "views/mirabilenet_fiber_nap_views.xml",
        "views/mirabilenet_fiber_port_views.xml",
        "views/mirabilenet_fiber_segment_views.xml",
        "views/mirabilenet_service_views.xml",
        "views/res_partner_views.xml",
        "views/maintenance_request_views.xml",
        "views/res_config_settings_views.xml",
        # Antes de los menús: los menús de importación abren las acciones de los asistentes.
        "wizards/mirabilenet_fiber_csv_import_views.xml",
        "wizards/mirabilenet_fiber_kml_import_views.xml",
        "wizards/mirabilenet_fiber_port_assign_views.xml",
        "wizards/mirabilenet_fiber_locate_views.xml",
        "views/mirabilenet_fibra_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mirabilenet_fibra/static/src/fiber_map/*",
        ],
    },
    "application": False,
    "installable": True,
}
