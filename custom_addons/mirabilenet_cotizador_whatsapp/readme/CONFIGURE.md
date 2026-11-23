- **Plantillas que hay que crear en Meta:**
  - `cotizacion`: encabezado de tipo documento; cuerpo con {{1}} cliente, {{2}} número y
    {{3}} total. El nombre se cambia en el parámetro
    `mirabilenet_cotizador.plantilla_cotizacion`.
  - `cotizacion_revisar` (aviso al vendedor): {{1}} persona, {{2}} número, {{3}} cliente.
- **Qué ofrece el bot:** la casilla «Ofrecer en el bot» de cada kit y de cada producto.
- **Quién cotiza por WhatsApp:** los usuarios con el permiso «Cotizador: cotizar y enviar» y
  con su WhatsApp cargado.
- **Flujos de n8n:** se generan con `documentacion/herramientas/generar_flujos_cotizacion.py`
  (17 y 15) y `generar_flujo_20_personal.py` (20). Copias en `documentacion/n8n/`.
