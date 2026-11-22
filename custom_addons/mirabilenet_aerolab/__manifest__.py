{
    "name": "MIRABILENET: AeroLab sobre Eventos",
    "version": "19.0.2.0.0",
    "summary": "Los cursos de drones son eventos de Odoo con entradas pagadas",
    "description": "Adapta Eventos: curso en preparación sin fecha, cupo y precio, carnet "
                   "único por curso y región. Detalle en readme/.",
    "category": "MIRABILENET",
    "author": "MIRABILENET",
    "license": "AGPL-3",
    "depends": ["mirabilenet_base", "website_event_sale", "event_min_seat"],
    "data": [
        "security/mirabilenet_aerolab_security.xml",
        "data/mirabilenet_aerolab_data.xml",
        "views/event_event_views.xml",
        "views/mirabilenet_aerolab_menus.xml",
    ],
    "application": False,
    "installable": True,
}
