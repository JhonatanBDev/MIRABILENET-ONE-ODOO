Cotizaciones de cámaras y redes por WhatsApp: las hace el bot para clientes e interesados, y
las pide el personal escribiendo «cotiza…».

- **Herramientas para los bots de n8n** (flujos 17 Ventas y 15 Soporte), en la API de n8n:
  - `GET /conversations/<id>/kits`: kits que se ofrecen y ciudades. Sin precios.
  - `GET /conversations/<id>/products?buscar=&ciudad=`: equipos publicados, con el precio de
    venta que calcula el motor y si hay en la ciudad.
  - `POST /conversations/<id>/quotation` (kit o pedido, ciudad, nombre): arma la cotización y
    le envía el PDF por la conversación.
- **La IA no pone precios.** Elige el kit o copia el pedido; los productos, el margen y los
  impuestos los pone el motor del cotizador.
- **Una cotización con alertas no sale sola.** Si falta stock, el precio es antiguo o el
  grabador no alcanza, queda en borrador, el bot dice que un asesor la confirma y al vendedor
  de la región le llega el aviso `cotizacion_revisar`. Un material cotizado con su precio de
  referencia no la frena.
- **El personal cotiza por WhatsApp** (flujo 20): «cotiza casa 4 cámaras para Juan 7xxxxxxx».
  Odoo arma la cotización y le manda el PDF con el botón «Enviar al cliente». También vale
  escribir «enviar COT-2026-0007». Solo la envía quien la pidió.
- **Desde Odoo:** en la cotización, «Enviarme por WhatsApp» y «Enviar al cliente por WhatsApp».
- **Envío al cliente:** dentro de la conversación si escribió en las últimas 24 horas; si no,
  con la plantilla de Meta `cotizacion`, que lleva el PDF en el encabezado.
- **Envíos por WhatsApp** (MIRABILENET > Cotizaciones): la cola, con su estado y su error.
