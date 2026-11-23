Personal y avisos de trabajo por WhatsApp.

**Plantilla del personal.** MIRABILENET > Usuarios > Importar personal. Una fila por persona:

- nombre, usuario, correo y WhatsApp;
- rol: uno de los que ya existen. «gerente» se entiende como gerencia y «subgerente» como
  administrador regional;
- región, sucursal, zonas que atiende y jefe directo.

Primero se revisa y después se carga. Lo que tiene problemas sale en un CSV de observaciones.
Pasa por las mismas barreras que la administración de usuarios. Los mismos datos se editan en
la ficha de cada usuario (Editar).

**Averías.** Al crearse una avería de un cliente (desde el servicio, desde «Ubicar cliente» o a
mano):

1. **Se asigna sola** al técnico que atiende la zona del cliente (la zona del nodo del
   servicio). Si hay varios, va al que tiene menos averías abiertas. Si nadie atiende la zona,
   va a un técnico de la región. Si no hay técnicos, va al encargado de la región (admin
   regional o NOC).
2. **Al técnico le llega un WhatsApp** con cliente, teléfono, dirección, caja NAP y puerto, el
   link de Google Maps a la caja y el diagnóstico de la caja: si hay más averías en esa caja, el
   problema probablemente está en la caja.
3. **El técnico responde con los botones** «Voy en camino», «Arreglado» o «No se pudo». También
   puede escribir con sus palabras.
   - **Arreglado:** la avería se cierra.
     - Al cliente le llega «servicio reparado».
     - Los demás técnicos de la zona reciben un aviso de que esa caja ya no tiene trabajo
       pendiente, o de cuántas averías quedan.
   - **No se pudo:** se le pide el motivo, se guarda en la avería y se le manda a su jefe.
4. **Recordatorios.** Si no responde en 1 hora, se le recuerda y se avisa a su jefe. Si sigue
   abierta después de 8 horas, se avisa al jefe. Las horas se configuran con los parámetros
   `mirabilenet.personal_horas_aceptar` y `mirabilenet.personal_horas_cerrar`.

**Tareas.** A quien le asignan una tarea en Proyectos (por ejemplo, un pasante) le llega por
WhatsApp, con los botones «Recibido» y «Terminada».

**Cómo se reparte el trabajo:**

- **Odoo decide y guarda todo.** Reconoce cuando el que escribe es del personal: su mensaje no
  abre una conversación de cliente ni pasa por el bot de ventas. Los botones funcionan aunque
  n8n no esté.
- **Lo que escriben con sus palabras** se le pasa a n8n (flujo «20 Personal»), si está
  configurado. n8n lo interpreta con IA y contesta con `POST /api/v1/messaging/n8n/personal/resultado`.
- **Sin n8n,** Odoo entiende «arreglado», «no se pudo» y «voy en camino».
- **Pasantes:** una tarea de pasantía se avisa cuando se publica (no al asignarla), con la
  plantilla `tarea_pasante`: «tienes una tarea nueva, revisa la plataforma», con el enlace y
  solo el botón «Recibido». «Terminada» no aplica: la pasantía se entrega en la plataforma.
