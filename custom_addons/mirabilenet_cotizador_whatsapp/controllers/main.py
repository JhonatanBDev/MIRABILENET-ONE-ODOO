from odoo import http

from odoo.addons.mirabilenet_whatsapp.controllers.n8n_api import (
    CONV, MirabilenetN8nApiController)


def _route(path, methods):
    return http.route(path, type="http", auth="public", methods=methods, csrf=False,
                      save_session=False)


class MirabilenetCotN8nApi(MirabilenetN8nApiController):
    """Herramientas del cotizador para los bots: las mismas reglas y el mismo token que el
    resto de la API de n8n."""

    @_route(CONV + "/kits", ["GET"])
    def conversation_kits(self, pk, **_kw):
        return self._call("conversation_kits", pk)

    @_route(CONV + "/products", ["GET"])
    def conversation_products(self, pk, **_kw):
        return self._call("conversation_products", pk, query=True)

    @_route(CONV + "/quotation", ["POST"])
    def conversation_quotation(self, pk, **_kw):
        return self._call("conversation_quotation", pk, body=True)
