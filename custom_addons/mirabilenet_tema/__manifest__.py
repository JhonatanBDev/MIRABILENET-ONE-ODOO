{
    "name": "MIRABILENET: Tema visual",
    "version": "19.0.1.0.0",
    "summary": "Colores de la marca y un estilo moderno y limpio en la parte interna de Odoo",
    "description": "Cambia los colores de Odoo por los del logo de MIRABILENET (azul noche, azul y "
                   "celeste), redondea esquinas, suaviza sombras y da aire a formularios, listas "
                   "y tarjetas. Respeta el modo oscuro de OCA web_dark_mode. Detalle en readme/.",
    "category": "MIRABILENET",
    "author": "MIRABILENET",
    "license": "AGPL-3",
    "depends": [
        "web",
        "web_dark_mode",
    ],
    "data": [],
    "assets": {
        # Variables de color: van antes de las de Odoo para que ganen (todas usan !default).
        "web._assets_primary_variables": [
            (
                "before",
                "web/static/src/scss/primary_variables.scss",
                "mirabilenet_tema/static/src/scss/primary_variables.scss",
            ),
        ],
        # En oscuro, los colores de la marca más claros van antes de los del modo claro.
        "web.assets_variables_dark": [
            (
                "before",
                "mirabilenet_tema/static/src/scss/primary_variables.scss",
                "mirabilenet_tema/static/src/scss/primary_variables.dark.scss",
            ),
        ],
        "web.assets_backend": [
            "mirabilenet_tema/static/src/scss/backend.scss",
        ],
        "web.assets_frontend": [
            "mirabilenet_tema/static/src/scss/login.scss",
        ],
    },
    "application": False,
    "installable": True,
}
