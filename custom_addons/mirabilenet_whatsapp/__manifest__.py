{
    "name": "MIRABILENET: WhatsApp",
    "version": "19.0.2.0.0",
    "summary": "Avisos de cobro, conversaciones y la API que usan los flujos de n8n",
    "description": "Bandeja de salida de avisos de cobro por la API de la nube de Meta: "
                   "plantillas aprobadas, consentimiento, bajas, horario, tope diario e "
                   "idempotencia. Detalle en readme/.",
    "category": "MIRABILENET",
    "author": "MIRABILENET",
    "license": "AGPL-3",
    "depends": ["mirabilenet_contratos", "crm"],
    "data": [
        "security/mirabilenet_whatsapp_security.xml",
        "security/ir.model.access.csv",
        "data/mirabilenet_whatsapp_data.xml",
        # Antes de las vistas y los menús: los formularios de chats y comprobantes tienen
        # botones que abren las acciones de estos asistentes, y los menús «Enviar aviso» y
        # «Simulador» también.
        "wizards/mirabilenet_whatsapp_send_wizard_views.xml",
        "wizards/mirabilenet_chat_wizard_views.xml",
        "wizards/mirabilenet_whatsapp_proof_reject_wizard_views.xml",
        "views/mirabilenet_whatsapp_message_views.xml",
        "views/mirabilenet_whatsapp_settings_views.xml",
        "views/mirabilenet_whatsapp_number_views.xml",
        "views/mirabilenet_whatsapp_template_views.xml",
        "views/mirabilenet_whatsapp_consent_views.xml",
        "views/mirabilenet_whatsapp_optout_views.xml",
        "views/mirabilenet_payment_qr_views.xml",
        "views/mirabilenet_conversation_views.xml",
        "views/mirabilenet_whatsapp_proof_views.xml",
        "views/mirabilenet_support_case_views.xml",
        "views/mirabilenet_integration_alert_views.xml",
        "views/mirabilenet_bot_settings_views.xml",
        "views/mirabilenet_retention_promo_views.xml",
        "views/mirabilenet_whatsapp_menus.xml",
    ],
    "application": False,
    "installable": True,
}
