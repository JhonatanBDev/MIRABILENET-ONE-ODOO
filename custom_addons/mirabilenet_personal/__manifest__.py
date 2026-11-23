{
    "name": "MIRABILENET: Personal y avisos de trabajo",
    "version": "19.0.1.0.0",
    "summary": "Plantilla del personal y avisos de trabajo por WhatsApp: averías por zona y tareas",
    "description": "Carga del personal desde una plantilla (rol, región, WhatsApp, zonas, jefe). "
                   "Las averías se asignan al técnico de la zona y le llegan por WhatsApp con "
                   "los datos de la caja NAP; él responde con botones o con sus palabras (n8n). "
                   "Avisa al cliente, a los demás técnicos y al jefe. Detalle en readme/.",
    "category": "MIRABILENET",
    "author": "MIRABILENET",
    "license": "AGPL-3",
    "depends": [
        "mirabilenet_whatsapp",
        "mirabilenet_fibra",
        "project",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/mirabilenet_staff_template_data.xml",
        "data/ir_config_parameter_data.xml",
        "data/ir_cron_data.xml",
        "views/mirabilenet_personal_views.xml",
        "views/mirabilenet_personal_menus.xml",
    ],
    "application": False,
    "installable": True,
}
