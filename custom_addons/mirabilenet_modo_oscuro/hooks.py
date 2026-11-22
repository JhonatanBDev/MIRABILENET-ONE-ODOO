def post_init_hook(env):
    """Los usuarios internos que ya existen pasan a seguir el modo del navegador.

    Los que se creen después lo heredan del valor por defecto de data/ir_default_data.xml.
    """
    users = env["res.users"].with_context(active_test=False).search([("share", "=", False)])
    settings_model = env["res.users.settings"]
    for user in users:
        settings_model._find_or_create_for_user(user).dark_mode_device_dependent = True
