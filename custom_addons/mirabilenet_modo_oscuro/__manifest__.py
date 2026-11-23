{
    "name": "MIRABILENET: Modo oscuro automático",
    "version": "19.0.1.0.1",
    "summary": "Odoo sigue el modo claro u oscuro del navegador, también en la pantalla de ingreso",
    "description": "Activa en todos los usuarios internos el modo oscuro según el dispositivo de "
                   "OCA web_dark_mode y oscurece la pantalla de ingreso, de registro y de cambio "
                   "de contraseña cuando el navegador está en oscuro. Detalle en readme/.",
    "category": "MIRABILENET",
    "author": "MIRABILENET",
    "license": "AGPL-3",
    "depends": [
        "web",
        "web_dark_mode",
    ],
    "data": [
        "data/ir_default_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "mirabilenet_modo_oscuro/static/src/scss/login_dark.scss",
        ],
    },
    "post_init_hook": "post_init_hook",
    "application": False,
    "installable": True,
}
