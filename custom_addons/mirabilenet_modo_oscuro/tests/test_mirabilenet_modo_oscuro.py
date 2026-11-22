from odoo.tests import HttpCase, new_test_user, tagged


@tagged("mirabilenet", "post_install", "-at_install")
class TestModoOscuro(HttpCase):
    def test_usuario_nuevo_sigue_al_navegador(self):
        user = new_test_user(self.env, "pasante_oscuro", groups="base.group_user")
        settings = self.env["res.users.settings"]._find_or_create_for_user(user)
        self.assertTrue(settings.dark_mode_device_dependent)

    def test_usuarios_existentes_siguen_al_navegador(self):
        admin = self.env.ref("base.user_admin")
        self.assertTrue(admin.dark_mode_device_dependent)

    def test_navegador_oscuro_recibe_backend_oscuro(self):
        new_test_user(self.env, "interno_oscuro", groups="base.group_user")
        self.authenticate("interno_oscuro", "interno_oscuro")
        response = self.url_open("/odoo", headers={"Sec-CH-Prefers-Color-Scheme": "dark"})
        self.assertIn("web.assets_web_dark", response.text)

    def test_pantalla_de_ingreso_tiene_estilos_oscuros(self):
        response = self.url_open("/web/assets/_/web.assets_frontend.min.css")
        self.assertEqual(response.status_code, 200)
        css = response.text
        self.assertIn("prefers-color-scheme: dark", css)
        self.assertIn(".oe_reset_password_form", css)
