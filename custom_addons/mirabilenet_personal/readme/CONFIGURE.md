## 1. Plantillas en Meta (obligatorio para enviar de verdad)

WhatsApp solo deja escribirle primero a una persona con plantillas aprobadas. Créelas en Meta
Business:
- Administrador de WhatsApp > Plantillas de mensajes;
- categoría **Utilidad**, idioma **Español (es)**;
- los nombres y el orden de las variables tienen que ser los de MIRABILENET > Usuarios >
  Plantillas de avisos;
- los botones son de **respuesta rápida**, en el orden indicado.

**averia_asignada.** Botones: «Voy en camino», «Arreglado», «No se pudo».
```
Hola {{1}}, tiene una avería asignada ({{2}}).
Cliente: {{3}} · Tel: {{4}}
Dirección: {{5}}
Caja NAP: {{6}} · Puerto {{7}}
{{8}}
Cómo llegar: {{9}}
```

**averia_recordatorio.** Mismos botones.
```
{{1}}, la avería {{2}} de {{3}} (caja {{4}}) sigue sin respuesta hace {{5}} hora(s).
```

**averia_resuelta.** Sin botones.
```
{{1}}: {{2}} resolvió la avería {{3}} (caja {{4}}). Quedan {{5}} avería(s) abiertas en esa caja y {{6}} en la zona.
```

**averia_no_resuelta.** Sin botones.
```
{{1}}: {{2}} no pudo resolver la avería {{3}} de {{4}} (caja {{5}}). Motivo: {{6}}
```

**averia_sin_atender.** Sin botones.
```
{{1}}: la avería {{3}} de {{4}}, asignada a {{2}}, lleva {{5}} hora(s) sin resolverse.
```

**tarea_asignada.** Botones: «Recibido», «Terminada».
```
Hola {{1}}, tiene una tarea nueva: {{2}} (proyecto {{3}}). Fecha límite: {{4}}. La asignó {{5}}.
```

**Aviso al cliente.** En MIRABILENET > Mensajería > Plantillas, cree la plantilla del evento
«Servicio reparado tras una avería», con las variables `cliente, sucursal`. Por ejemplo:
«Hola {{1}}, su servicio de internet ya fue reparado. Cualquier consulta, escríbanos. {{2}}».

## 2. El personal

Cargue la plantilla del personal (Importar personal), o complete en cada usuario:
- su WhatsApp;
- las zonas que atiende;
- su jefe directo.

Los servicios tienen que tener un nodo con su zona: de ahí sale a qué técnico le toca.

## 3. n8n (opcional, para entender lo que escriben)

Importe el flujo «MIRABILENET · 20 Personal» (`documentacion/n8n/20_personal.json`) y actívelo.
En Odoo, ponga el parámetro `mirabilenet.n8n_staff_webhook_url` con la dirección de su webhook,
por ejemplo `http://127.0.0.1:5679/webhook/mirabilenet-personal`. Usa el mismo token y el mismo
secreto que el resto de la API de n8n.
