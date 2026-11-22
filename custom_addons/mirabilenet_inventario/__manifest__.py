{
    "name": "MIRABILENET: Inventario",
    "version": "19.0.1.0.0",
    "summary": "Almacenes por región, series y movimientos sobre el inventario de Odoo",
    "description": "Usa el módulo de inventario de Odoo. Agrega la región de cada "
                   "almacén, la situación de cada serie (almacén, técnico, cliente, "
                   "reparación, baja) y los tipos de movimiento de MIRABILENET. "
                   "Detalle en readme/.",
    "category": "MIRABILENET",
    "author": "MIRABILENET",
    "license": "AGPL-3",
    "depends": ["mirabilenet_isp", "stock"],
    "data": [
        "security/mirabilenet_inventario_security.xml",
        "security/ir.model.access.csv",
        "data/mirabilenet_inventario_data.xml",
        "views/stock_lot_views.xml",
        "views/stock_move_views.xml",
        "views/stock_quant_views.xml",
        "views/product_template_views.xml",
        "views/stock_warehouse_views.xml",
        # Antes de los menús: «Registrar movimiento» abre la acción del asistente.
        "wizards/mirabilenet_inventory_move_wizard_views.xml",
        "views/mirabilenet_inventario_menus.xml",
    ],
    "application": False,
    "installable": True,
}
