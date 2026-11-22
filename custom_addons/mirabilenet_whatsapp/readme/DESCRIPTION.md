Fase 6 de la migración de MIRABILENET ONE a Odoo 19: avisos de cobro, conversaciones,
comprobantes, solicitudes de atención, ajustes del asistente y **la API que usan los flujos
de n8n, con el mismo contrato que antes**.

**Los flujos de n8n no se tocaron.** Siguen apuntando al sistema anterior hasta el día del
cambio (fase 10): ese día, el nombre `api:8000` de la red de Docker pasa a apuntar a Odoo.

## El contrato con n8n

Odoo expone las mismas 22 rutas bajo `/api/v1/messaging/n8n/`, con los mismos parámetros,
campos de respuesta y códigos de error (`no_es_cliente`, `es_cliente`, `fuera_de_ventana`,
`atiende_una_persona`, `cerrada`, `dado_de_baja`, `mensajeria_apagada`, `sin_numero`,
`limite_por_hora`, `clave_en_uso`...). Se comprobó contra los JSON de `n8n-workflows/`: todas
las rutas que llaman los flujos existen aquí.

Odoo envía al flujo 10 el mismo evento `mensaje_entrante`, firmado igual: cabecera
`X-Mirabilenet-Signature` y un JWT HS256 de 2 minutos con el SHA-256 del cuerpo.

Los dos secretos viven en el entorno del servidor, fuera de la base:

| Variable | Qué es | Credencial en n8n |
|---|---|---|
| `MIRABILENET_N8N_API_TOKEN` | Token que presenta n8n | «MIRABILENET API» |
| `MIRABILENET_N8N_WEBHOOK_SECRET` | Secreto de la firma (32 caracteres o más) | «MIRABILENET Webhook (JWT)» |

Deben ser **los mismos valores** que hoy tiene el sistema anterior (`N8N_API_TOKEN` y
`N8N_WEBHOOK_SECRET`), para no tocar las credenciales de n8n. Sin token configurado, la API
queda cerrada.

Parámetro del sistema: `mirabilenet.n8n_inbound_webhook_url`
(`http://n8n:5678/webhook/mirabilenet-entrante`).

## Arquitectura

```
account.move._mirabilenet_notify(evento)             <- los cobros solo avisan aquí
        |
mirabilenet.whatsapp.message._enqueue(...)           <- todas las reglas de envío
        |   (fila en la bandeja de salida)
tarea programada  ->  _dispatch()
        |
whatsapp/gateway.py  MetaGateway                      <- única puerta hacia Meta
        |-- RealMetaGateway -> whatsapp/cloud_api.py -> Graph API
        `-- FakeMetaGateway (doble para desarrollo y pruebas)
```

La carpeta `whatsapp/` no importa Odoo. `cloud_api.py` es el cliente del sistema anterior,
copiado sin cambios. Los cobros no dependen de este módulo: se engancha en el punto que
`mirabilenet_contratos` deja para eso en la factura (`account.move._mirabilenet_notify`), al
que llama el contrato recurrente con `aviso_emitido` cada vez que publica una factura emitida.

No se usó ningún módulo de terceros: la pasarela de WhatsApp de la OCA no existe para Odoo 19.

## Reglas de las conversaciones (probadas)

- El mensaje entrante se registra antes de pasarlo a n8n y no se duplica si Meta lo repite.
- El evento hacia n8n no lleva datos del cliente: solo si es cliente y el id de la
  conversación. Las herramientas reciben ese id, nunca un teléfono.
- Las respuestas del asistente exigen la ventana de 24 horas, que no atienda una persona, que
  no haya baja, una clave por envío y el tope de 30 por hora. No esperan el horario ni cuentan
  para el tope diario.
- Pasar a una persona abre (o reutiliza) la solicitud, avisa al contacto y pausa el asistente.
  Al resolverla, la conversación vuelve al asistente.
- Una persona responde desde el chat; el asistente queda en pausa.
- El simulador recorre el circuito completo sin salir a Meta y no aplica las palabras de baja.
- **Comprobantes**: recibir el archivo no registra un pago ni reactiva nada. Verificar es de
  una persona, contra un aviso y en una caja activa de la región de ese aviso. Un comprobante
  del simulador no se puede verificar. El cliente recibe el resultado por el chat si la
  ventana sigue abierta, o por plantilla si no.
- El asistente solo ofrece planes activos, publicados y con precio, y promociones de retención
  cargadas y vigentes. La organización que ve es pública: sin nodos ni datos internos.
- Interruptores, modelo y estilo del asistente: solo los cambia un usuario con alcance global.
  El cupo se mide (respuestas por modelo y lo que respondió Google), nunca se estima.
- Si n8n no recibe un evento tras cuatro intentos, queda una alerta: no pasa en silencio.

## Reglas de los avisos de cobro (probadas)

- Todo mensaje que inicia la empresa sale por una **plantilla aprobada por Meta**. Las
  variables salen de una lista cerrada; una plantilla no puede pedir otra cosa.
- **Horario** (por defecto 08:00–20:00, hora de Bolivia): fuera de él, el mensaje espera en
  cola. No se pierde ni se envía.
- **Tope por cliente y día** (por defecto 2).
- **Bajas**: `BAJA`, `STOP`, `SALIR` y las demás frases registran la baja, descartan lo
  pendiente y no se vuelve a escribir. «Quiero dar de baja mi servicio» no es una baja de
  mensajes.
- **Consentimiento**: no se exige un registro por cliente, porque al contratar el servicio
  se le informa que se le puede contactar (decisión del 20/11/2026). La opción «Exigir
  consentimiento registrado» existe en Ajustes, apagada, por si algún día hace falta; con ella
  encendida no se escribe sin registro, y un registro nunca se crea en lote.
- **Silencio** en números en coexistencia: si una persona escribió al cliente hace poco, el
  aviso automático no sale. De lo que escribió la persona se guarda cuándo, no el texto.
- **Idempotencia**: cada mensaje lleva una clave (evento + aviso). Repetir la tarea del día no
  escribe dos veces.
- **Un fallo de mensajería nunca frena la cobranza**: un cliente sin número, sin plantilla o
  con Meta caído no impide emitir el resto del período.
- **Reintentos** solo para los errores que Meta marca como pasajeros, con tope.
- **Envío manual**: sale ya, pero no se salta bajas, tope ni región, y exige
  un aviso con saldo y un tipo de aviso que corresponda a su vencimiento.
- **Remitente compartido**: uno solo, lo administra un usuario con alcance global, y
  compartirlo no comparte datos (región, sucursal y QR siguen siendo los del cliente).
- **Estados de entrega** de Meta: nunca retroceden.
- La **bitácora no se edita ni se borra**. Seguimiento cuenta solo enviado, entregado o leído.
- Token de Meta, secreto de la aplicación y token del webhook se guardan **cifrados**.
- Todo aislado por región; el pasante no ve nada.
