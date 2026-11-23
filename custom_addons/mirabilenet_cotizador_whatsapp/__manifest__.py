{
    "name": "MIRABILENET: Cotizaciones por WhatsApp",
    "version": "19.0.1.0.0",
    "summary": "El bot ofrece y cotiza equipos, y el personal cotiza y envía el PDF por WhatsApp",
    "description": "Herramientas del cotizador para los flujos de n8n (kits, equipos y "
                   "cotización), cotización pedida por el personal desde WhatsApp y envío del "
                   "PDF al trabajador y al cliente. Detalle en readme/.",
    "category": "MIRABILENET",
    "author": "MIRABILENET",
    "license": "AGPL-3",
    "depends": ["mirabilenet_cotizador", "mirabilenet_whatsapp", "mirabilenet_personal"],
    "data": [
        "security/ir.model.access.csv",
        "data/mirabilenet_cotizador_whatsapp_data.xml",
        "views/mirabilenet_cotizador_whatsapp_views.xml",
    ],
    "application": False,
    "installable": True,
}
