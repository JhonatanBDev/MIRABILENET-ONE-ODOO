{
    "name": "MIRABILENET: Importar cartera",
    "version": "19.0.1.2.0",
    "summary": "Asistente para cargar una planilla de clientes, servicios, PPPoE y ONU",
    "description": "Sube la planilla de cartera de una región, la corrige, muestra un resumen y "
                   "crea los planes que falten, los clientes, los servicios activos, las cuentas "
                   "PPPoE, las ONU y la caja NAP y el puerto de cada servicio, con una lista "
                   "para revisar en campo. Detalle en readme/.",
    "category": "MIRABILENET",
    "author": "MIRABILENET",
    "license": "AGPL-3",
    "depends": [
        "mirabilenet_isp",
        "mirabilenet_inventario",
        "mirabilenet_fibra",
    ],
    "data": [
        "security/ir.model.access.csv",
        # Antes de los menús: el menú abre la acción del asistente.
        "wizards/mirabilenet_portfolio_import_views.xml",
        "views/mirabilenet_cartera_menus.xml",
    ],
    "application": False,
    "installable": True,
}
