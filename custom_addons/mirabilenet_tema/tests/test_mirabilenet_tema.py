from odoo.tests import HttpCase, tagged


@tagged("mirabilenet", "post_install", "-at_install")
class TestTema(HttpCase):

    def _css(self, bundle):
        response = self.url_open("/web/assets/_/%s.min.css" % bundle)
        self.assertEqual(response.status_code, 200, bundle)
        css = response.text.lower()
        # Si el SCSS no compila, Odoo entrega el error dentro del CSS.
        self.assertNotIn("css_error_message", css, bundle)
        return css

    def test_claro_usa_los_colores_del_logo(self):
        css = self._css("web.assets_web")
        self.assertIn("#006db7", css)   # azul de la marca (botones y acciones)
        self.assertIn("#0f172a", css)   # azul noche (barra superior)

    def test_oscuro_usa_el_celeste(self):
        css = self._css("web.assets_web_dark")
        self.assertIn("#00abda", css)
        self.assertIn("#0b1220", css)

    def test_pantalla_de_ingreso_es_una_tarjeta(self):
        css = self._css("web.assets_frontend")
        self.assertIn("form.oe_login_form", css)
        self.assertIn("border-radius:14px", css.replace(" ", ""))
