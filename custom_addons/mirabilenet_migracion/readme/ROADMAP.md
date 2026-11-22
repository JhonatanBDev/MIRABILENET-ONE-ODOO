## Lo que no hace todavía

- **Movimientos históricos de inventario:** no se recrean, porque cambiarían las existencias.
  Las existencias se cargan como están y la historia queda en el sistema anterior.
- **Tokens de Meta:** el token de acceso, el secreto de la app y el de verificación están
  cifrados. La mensajería migrada queda apagada y los tokens se cargan a mano el día del cambio.
- **Alertas de n8n:** no se migran, porque son técnicas.
- **AeroLab:**
  - lista de espera y preinscripción pasan como «sin confirmar»;
  - el monto pagado a mano no tiene dónde ir y se reporta;
  - un curso sin fecha queda con fecha provisional, sin confirmar y sin publicar.
- **Pasantías:** una tarea sin proyecto no tiene dónde ir y se rechaza.
- **Recibos por caja:** el punto 4 de la guía (recibos con número original y secuencia de cada
  caja continuada) no aplica tal cual, porque Odoo no tiene cajas con correlativo propio. El
  número queda en el pago.
- La secuencia de códigos de cliente de Odoo no se ajusta sola: después de migrar hay que
  ponerla por encima del último código del sistema anterior.
- Probado solo con tablas de prueba con el mismo esquema (8 pruebas, todas las etapas). Falta
  correrlo contra la copia real que indique el usuario, con las copias de `media` y
  `private_media`.
