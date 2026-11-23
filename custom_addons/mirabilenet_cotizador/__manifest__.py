{
    "name": "MIRABILENET: Cotizador de CCTV y redes",
    "version": "19.0.1.1.0",
    "summary": "Cotizaciones de CCTV y redes desde kits o texto libre, con el motor de precios del "
               "Cotizador DigiCorp",
    "description": "Motor del Cotizador DigiCorp (referencia/) en Odoo: catálogo del proveedor, "
                   "kits, recargos por categoría, redondeo, IVA + IT, cálculo de disco, PDF para el "
                   "cliente sin datos internos, etapas y precios congelados. Detalle en readme/.",
    "category": "MIRABILENET",
    "author": "MIRABILENET",
    "license": "AGPL-3",
    "depends": ["mirabilenet_base", "mirabilenet_isp", "sale_management"],
    "data": [
        "security/mirabilenet_cotizador_security.xml",
        "security/ir.model.access.csv",
        "data/mirabilenet_cotizador_base_data.xml",
        "data/mirabilenet_cotizador_data.xml",
        "data/mirabilenet_cot_markup_data.xml",
        "views/mirabilenet_cotizador_views.xml",
        "report/mirabilenet_cot_report.xml",
        "views/mirabilenet_cotizador_menus.xml",
    ],
    "application": False,
    "installable": True,
}
