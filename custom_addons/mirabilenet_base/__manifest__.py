{
    "name": "MIRABILENET: Organización y usuarios",
    "version": "19.0.1.0.0",
    "summary": "Regiones, sucursales, zonas, nodos, roles y aislamiento por región",
    "description": "Base de los módulos de MIRABILENET: organización por regiones, roles del "
                   "personal, aislamiento por región y auditoría. Detalle en readme/.",
    "category": "MIRABILENET",
    "author": "MIRABILENET",
    "license": "AGPL-3",
    "depends": ["base", "mail", "auth_signup"],
    "data": [
        "security/mirabilenet_base_security.xml",
        "security/ir.model.access.csv",
        "views/mirabilenet_region_views.xml",
        "views/mirabilenet_branch_views.xml",
        "views/mirabilenet_zone_views.xml",
        "views/mirabilenet_node_views.xml",
        "views/mirabilenet_audit_log_views.xml",
        "views/res_users_views.xml",
        # Antes de los menús: el menú «Nuevo usuario» abre la acción del asistente.
        "wizards/mirabilenet_user_wizard_views.xml",
        "views/mirabilenet_base_menus.xml",
    ],
    "demo": ["demo/mirabilenet_demo.xml"],
    "application": True,
    "installable": True,
}
