"""El dashboard es la pantalla de inicio de los usuarios de MIRABILENET que no eligieron otra."""

ACTION = "mirabilenet_dashboard.action_mirabilenet_dashboard"


def post_init_hook(env):
    action = env.ref(ACTION)
    group = env.ref("mirabilenet_base.group_mirabilenet_user")
    users = env["res.users"].with_context(active_test=False).search(
        [("share", "=", False), ("action_id", "=", False), ("group_ids", "in", group.ids)])
    users.write({"action_id": action.id})


def uninstall_hook(env):
    action = env.ref(ACTION, raise_if_not_found=False)
    if action:
        env["res.users"].with_context(active_test=False).search(
            [("action_id", "=", action.id)]).write({"action_id": False})
