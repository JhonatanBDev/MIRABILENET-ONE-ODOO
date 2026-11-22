{
    "name": "MIRABILENET: Migración desde el sistema anterior",
    "version": "19.0.1.0.0",
    "summary": "Guion repetible, por etapas y con sumas de control, desde la base de Django",
    "description": "Lee una copia de la base del sistema anterior y crea lo equivalente en Odoo. "
                   "Detalle en readme/.",
    "category": "MIRABILENET",
    "author": "MIRABILENET",
    "license": "AGPL-3",
    "depends": ["mirabilenet_contratos", "mirabilenet_inventario", "mirabilenet_whatsapp",
                "mirabilenet_web", "mirabilenet_aerolab", "mirabilenet_pasantias"],
    "data": ["data/mirabilenet_migracion_data.xml"],
    "application": False,
    "installable": True,
}
