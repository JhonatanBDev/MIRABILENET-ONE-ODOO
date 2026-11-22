## Puesta en marcha

1. Clave maestra en el servidor (fuera de Git y de la base):
   variable de entorno `MIRA_SIAT_MASTER_KEY=<valor largo y aleatorio>`.
   Si se pierde, los secretos guardados no se pueden recuperar.
2. Instalar: `odoo-bin -c odoo.conf -d <base> -i mira_sale_siat`.
3. Dar a los usuarios un rol de *Mira_Sale SIAT* (Emisor, Supervisor o
   Administrador SIAT) y, a quien corresponda, *Emisión con fecha anterior*.
4. Contabilidad > SIAT (Mira_Sale) > Configuración SIAT > **Asistente de
   configuración**: NIT, conexión, sucursales y puntos de venta, token, CUIS,
   CUFD, catálogos y parámetros de emisión.
5. Homologar productos (pestaña SIAT) y clientes (tipo de documento).
6. En los diarios de banco y caja, indicar el método de pago SIAT; en el diario
   de ventas, el documento sector si difiere del de la empresa.
7. Publicar una factura de cliente y pulsar **Emitir al SIAT**.

La contabilidad de la empresa debe llevarse en bolivianos: los importes
fiscales se expresan en la moneda de la empresa.
