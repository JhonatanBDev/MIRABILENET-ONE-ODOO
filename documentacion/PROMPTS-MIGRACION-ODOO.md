# Prompts para migrar MIRABILENET ONE a Odoo Community

**Estado:** guía de trabajo. Nada de esto está programado.
**Fecha:** 19 de noviembre de 2026.
**Idea central:** usar lo que Odoo Community y su comunidad (OCA) ya traen hecho, adaptarlo por herencia y programar solo lo que no existe.

---

## 1. Antes de empezar: qué se ahorra y qué no

Odoo ahorra trabajo en la parte administrativa. La parte que hace distinto a este sistema se programa igual, ahora como módulos de Odoo.

| Se aprovecha casi hecho | Se programa igual |
|---|---|
| Contactos y prospectos (CRM) | Red: routers MikroTik, PPPoE, WireGuard, subredes, cortes y reconexiones |
| Productos (los planes) | Ciclo de cobro por región, prepago y pospago, con prorrateo |
| Inventario | Recibo interno con correlativo sin huecos y caja con arqueo |
| Facturas y pagos básicos | WhatsApp: plantillas, reglas de envío, comprobantes QR y su verificación |
| Usuarios, grupos y permisos | La API que usan los flujos de n8n (asistente de soporte y ventas) |
| Sitio web y formularios | Pasantías |
| Historial de cambios en cada registro | Facturación con el SIAT: ya hecha en el módulo propio `mira_sale_siat` |

**Lo que no se toca: las automatizaciones de n8n.** Los flujos del asistente de WhatsApp ya funcionan y se conservan tal como están (sección 4). No se reescriben en Odoo ni se editan: Odoo se adapta a ellos.

Lo que se pierde al migrar:

- Las 571 pruebas automáticas actuales. Documentan reglas de negocio; hay que volver a escribirlas en Odoo.
- El panel en Next.js. Odoo trae su propia interfaz.
- Tiempo de operación en paralelo, y una migración de los datos que ya están en producción.

**La fase 0 existe para comprobar esto con poco gasto.** Si al terminarla resulta que los módulos de la comunidad no cubren lo esperado para la versión elegida, conviene detenerse y reconsiderar el camino híbrido: Odoo solo para contabilidad, inventario y CRM, y el sistema actual para red, cobros y WhatsApp, conectados por API.

## 2. Cómo usar este documento

1. El repositorio de los módulos de Odoo ya existe: `C:\ING.SISTEMAS\SISTEMAS_Y_PROYECTOS\odoo`, con los módulos propios en `custom_addons\`. No se trabaja dentro del repositorio del sistema actual.
2. Abre **una sesión nueva de Claude Code por fase**. Sesiones cortas gastan menos y se equivocan menos.
3. En cada sesión pega primero el **prompt base** (sección 5) y después el prompt de la fase.
4. Reemplaza `RUTA_ACTUAL` por la carpeta del sistema actual. La sesión lo lee solo como referencia.
5. No pases a la fase siguiente si las pruebas de la actual no pasan.
6. Al cerrar cada fase, pide a la sesión que actualice `ESTADO.md` en el repositorio nuevo: qué quedó hecho, qué módulos se reutilizaron y qué quedó pendiente. La sesión siguiente empieza leyéndolo.

Los nombres de módulos de la comunidad que aparecen aquí son **candidatos a verificar en la fase 0**. Cambian de una versión de Odoo a otra, y algunos no existen para la versión más nueva.

## 3. Equivalencias: de dónde sale cada parte

Los módulos propios llevan el prefijo `mirabilenet_`; se puede cambiar por otro en el prompt base.

| App actual | Modelos actuales | Base en Odoo Community | Módulo propio |
|---|---|---|---|
| `core` | Organization, Region, Branch, Zone, Node, User, AuditLog, PreferenciasPanel | `base` (empresa, usuarios, grupos, reglas de registro), `mail` (historial) | `mirabilenet_base`: región, sucursal, zona, nodo, grupos por rol, regla de registro por región. PreferenciasPanel se descarta: Odoo guarda las preferencias del usuario |
| `crm` | Customer, CustomerContact, Contract | `contacts` (`res.partner`), `crm`; contratos recurrentes de OCA (repositorio `contract`), a verificar | Campos del cliente dentro de `mirabilenet_base` o `mirabilenet_isp` |
| `isp` | Plan, NetworkSubnet, Router, EnrollmentToken, RouterConfigChange, Service, PPPoEAccount, ServiceRosterData, ServiceStateTransition | `product` (el plan es un producto de tipo servicio) | `mirabilenet_isp`: todo lo de red. Se programa completo |
| `billing` | CashRegister, ReceiptSequence, CashSession, Charge, Payment, PaymentAllocation, Receipt, FiscalDocument, Expense | `account` (facturas, pagos, secuencias); contratos de OCA para la recurrencia, a verificar | `mirabilenet_cobros`: ciclo regional, prorrateo, recibo interno, caja. FiscalDocument ya lo cubre `mira.siat.invoice` de `mira_sale_siat` |
| `inventory` | Warehouse, InventoryItem, InventorySerial, InventoryStock, InventoryMovement | `stock` (almacenes, productos, series, existencias, movimientos) | Solo datos y permisos |
| `messaging` | WhatsAppSettings, BranchWhatsAppNumber, MessageTemplate, WhatsAppMessage, WhatsAppOptOut, ActividadAgente, WhatsAppConsentimiento, RegionalPaymentQR, WhatsAppProof, WhatsAppSupportCase, Conversacion, MensajeConversacion, AlertaIntegracion, AjustesBotIA, PromocionRetencion | `mail`; pasarela de WhatsApp de OCA (repositorio `social`), a verificar. El módulo oficial de WhatsApp es de Enterprise | `mirabilenet_whatsapp`: se programa casi completo. n8n queda igual: Odoo solo expone la misma API |
| `web` | SiteSettings, Ventaja, Cifra, Aliado, Service, CoverageLocality, Project, Faq, Lead, DocumentoLegal | `website`, `website_crm` (el Lead pasa a `crm.lead`) | `mirabilenet_web`: cobertura, planes publicados, textos legales con versión |
| `aerolab` | AeroLabSettings, DroneCourse, CourseEnrollment | `website_event` o `website_slides`, a decidir en la fase 7 | Adaptación menor |
| `pasantias` | Pasantia, Proyecto, Recurso, Tarea, ItemChecklist, Asignacion, ItemMarcado, Archivo, InformeAvance, Comentario, AdjuntoComentario, AvisoWhatsApp | `project` (proyectos, tareas, comentarios, adjuntos) | `mirabilenet_pasantias`: pasantía, lista de puntos, entrega y revisión, informe de avance |
| `panel` | (sin modelos: indicadores) | Vistas gráficas, pivote y tableros | `mirabilenet_indicadores` |

## 4. Lo que ya está hecho en n8n y no se toca

Los flujos de n8n están en `n8n-workflows/` del sistema actual, exportados en JSON. Funcionan bien y **no forman parte de la migración**: no se editan, no se regeneran y no se reemplazan por automatizaciones de Odoo (acciones automáticas, correo o un asistente propio).

### Avance actual

Estado según `n8n-workflows/README.md`:

| Flujo | Qué hace | Estado |
|---|---|---|
| 00 Prueba de conexión | Comprueba que n8n llega a la API | Listo |
| 10 Entrada de mensajes | Recibe cada mensaje, valida la firma (JWT y hash del cuerpo), contesta enseguida y decide si le toca al asistente | Listo |
| 11 Enviar mensaje | Subflujo que pide enviar la respuesta: texto, botones o lista | Listo |
| 12 Eco de prueba | Solo para probar el circuito a mano | Listo |
| 13 Atender comprobante | Acuse con el número de aviso, lista para elegir el aviso o pedido de reenvío | Listo |
| 14 Asociar comprobante | Asocia el comprobante al aviso que eligió el cliente y le confirma | Listo |
| 15 Agente de soporte | Responde a clientes: avisos, comprobantes, plan y contrato, cambio de plan, QR de pago, retención ante una baja, sucursales y zonas | Probado |
| 16 Derivar a persona | Abre o reutiliza la solicitud, manda el acuse y pausa el asistente | Probado |
| 17 Agente de ventas | Atiende a quien no es cliente: planes de todas las regiones, cobertura y registro del interesado para un asesor | Probado |
| 19 Alertas de errores | Deja cada falla de los demás flujos en Mensajería → Alertas n8n | Listo |

También funciona hoy, y depende de esos flujos:

- El verificador sin IA de los flujos 15 y 17: bloquea la respuesta si trae un número que no vino de la API, o si dice que registró datos sin haberlos registrado.
- El simulador del panel, que prueba el circuito completo sin salir a WhatsApp.
- Los interruptores de soporte y de ventas, el modelo principal y el de respaldo, y el paso a una persona cuando se agota el cupo.
- El estilo del asistente y el texto «Quiénes somos», editables desde el panel.
- Las promociones de retención: una sola oferta, una sola vez, sin demorar la baja.
- El paso a una persona con confirmación del cliente, sin botón.

### Qué debe cumplir Odoo para no tocar n8n

Los flujos tienen la dirección de la API escrita en sus nodos (`http://api:8000/api/v1/messaging/n8n/...`). Para no editar ni un JSON:

1. **Misma dirección.** Dentro de la red de Docker, Odoo (o un proxy delante de Odoo) responde con el nombre `api` en el puerto `8000`.
2. **Mismas rutas**, con los mismos parámetros, campos de respuesta y códigos de error:
   - `GET /conversations/<id>/history`, `/charges`, `/proofs`, `/service`, `/plans`, `/sales`, `/organization`, `/retention-offers`
   - `POST /conversations/<id>/lead`, `/handoff`, `/qr`, `/proofs/<comprobante>/charge`
   - `POST /messages`, `POST /ia/agotado`, `POST /alerts` y `GET /charges`
   - Rechazos `409` con su `codigo`: `no_es_cliente`, `es_cliente`, `fuera_de_ventana`, `atiende_una_persona`, `cerrada`, `dado_de_baja`, `mensajeria_apagada`, `sin_numero`, `limite_por_hora`, `clave_en_uso`.
3. **Mismo evento de entrada** hacia el flujo 10 (`mensaje_entrante`, con `conversacion`, `contacto`, `mensaje`, `manejado_por_sistema`, `comprobante` e `ia`), enviado a la misma dirección del webhook y firmado igual: JWT HS256 de 2 minutos que lleva el SHA-256 del cuerpo.
4. **Mismas credenciales por nombre**: «MIRABILENET API» (cabecera `Authorization: Bearer <token>`) y «MIRABILENET Webhook (JWT)». Odoo valida ese mismo token y firma con ese mismo secreto; en n8n no se cambia nada.
5. **Envíos idempotentes por `clave`**, igual que hoy.
6. **Identificadores coherentes.** n8n no guarda identificadores: los recibe en cada evento. Pero una lista de avisos enviada antes del cambio lleva los identificadores viejos; la fase 9 decide si se conservan los de avisos y comprobantes o si esas listas pendientes se vuelven a enviar.

El contrato completo, con ejemplos, está en `n8n-workflows/README.md`. Cualquier diferencia rompe un flujo que hoy funciona; por eso la fase 6 se cierra con una prueba por ruta y con el simulador, no solo con pruebas unitarias.

## 5. Prompt base

Se pega al inicio de **todas** las sesiones.

```text
Vas a construir módulos de Odoo Community para reemplazar MIRABILENET ONE, la plataforma de
gestión de MIRABILENET, proveedor de internet y videovigilancia de Bolivia. El sistema actual
(Django) está en RUTA_ACTUAL: léelo solo como referencia,
no lo modifiques. Empieza leyendo ESTADO.md de este repositorio, si existe.

Reglas de trabajo, sin excepciones:

1. REUTILIZAR ANTES QUE PROGRAMAR. Antes de escribir un modelo o una vista, busca si un módulo
   oficial de Odoo Community o de la OCA ya lo resuelve para la versión que usamos. Dime qué
   encontraste, de dónde, bajo qué licencia y si sirve tal cual, adaptado o no sirve. Solo crea un
   modelo nuevo cuando no exista nada aprovechable.
2. ADAPTAR POR HERENCIA. Nunca edites el código de Odoo ni de un módulo de terceros. Extiende con
   _inherit, vistas heredadas (xpath) y módulos propios con prefijo mirabilenet_.
3. NO INVENTES. No supongas nombres de módulos, modelos ni campos: compruébalos en el código de la
   versión instalada. Si no puedes comprobar algo, dilo. No uses módulos de Enterprise.
4. REGLAS DE NEGOCIO QUE NO SE PIERDEN:
   - Los datos no se inventan: si falta un precio, una fecha o un cupo, queda vacío y se dice.
   - Un indicador sin medición muestra «—» y el motivo, nunca un 0.
   - Aislamiento por región: un usuario regional solo ve y modifica lo de su región. Se implementa
     con reglas de registro (ir.rule), no solo ocultando menús.
   - Las acciones críticas quedan registradas con quién, cuándo y qué cambió.
   - Pagos y envíos son idempotentes: un reintento no duplica nada.
   - Los montos usan campos Monetary o Decimal, nunca float sin precisión.
   - Se desactiva, no se borra, cuando borrar perdería el rastro.
   - Los cambios de estado se hacen con botones o acciones, no editando el campo.
5. TODO EN ESPAÑOL (es-BO): nombres visibles, ayudas, mensajes de error y documentación. Tono
   directo, sin jerga de marketing.
6. CADA MÓDULO LLEVA: pruebas (TransactionCase) de sus reglas de negocio, datos de demostración
   ficticios, permisos (ir.model.access.csv y reglas de registro) y un README.
7. Antes de programar, preséntame un plan corto: qué se reutiliza, qué se hereda y qué se crea.
   Espera mi aprobación.
8. Al terminar, ejecuta las pruebas, muéstrame el resultado tal cual y actualiza ESTADO.md.
   No digas que algo funciona si no lo probaste.
9. Nunca leas ni copies secretos del sistema actual: carpetas secrets/, env/, wireguard/, archivos
   .env*, *.key, *.pem, backups/ y volcados *.dump.
10. NO TOQUES n8n. Los flujos de RUTA_ACTUAL/n8n-workflows/ funcionan y se conservan: no los
   modifiques, no los regeneres y no los reemplaces por automatizaciones de Odoo. Si algo de Odoo
   no encaja con lo que n8n espera, se cambia Odoo.
```

## 6. Prompts por fase

### Fase 0 — Entorno y comprobación de módulos

```text
Fase 0. Objetivo: saber, con evidencia, qué módulos existentes vamos a reutilizar. En esta fase
no se programa ningún módulo propio.

1. La versión ya está decidida: Odoo Community 19.0, con el código fuente en este repositorio.
2. El entorno local ya existe y no usa Docker: Windows, entorno virtual env\, PostgreSQL local y
   odoo.conf. Docker se deja para el despliegue al VPS (fase 10). Los módulos de terceros van en
   una carpeta aparte de custom_addons, agregada a addons_path.
3. Para cada necesidad de esta lista, busca el módulo, comprueba que exista para la versión
   elegida, instálalo en una base de prueba y pruébalo a mano. ESTADO.md ya trae una primera
   comprobación hecha solo leyendo los manifiestos:
   - contratos o suscripciones con cobro recurrente (candidato: OCA, repositorio «contract»);
   - envío y recepción de WhatsApp con la API de la nube de Meta (candidato: OCA, repositorio
     «social»);
   - tareas en segundo plano con reintentos (candidato: OCA, repositorio «queue»);
   - registro de auditoría de cambios (candidato: OCA, repositorio «server-tools»);
   - localización de Bolivia: plan de cuentas e impuestos;
   - facturación electrónica con el SIAT de Bolivia: resuelta con el módulo propio mira_sale_siat;
     no se busca otro.
4. Entrégame una tabla: necesidad, módulo, origen, licencia, versión, resultado de la prueba y
   veredicto (sirve, sirve adaptado, no sirve). Sin suposiciones.
5. Con esa tabla, dime qué fases de este plan se acortan y cuáles no, y si recomiendas seguir.
6. Escribe ESTADO.md con la versión elegida y la tabla.
```

### Fase 1 — Organización, usuarios y aislamiento por región

```text
Fase 1. Módulo mirabilenet_base.

Referencia en el sistema actual: RUTA_ACTUAL/app/apps/core/models.py (Region, Branch, Zone, Node,
User, AuditLog) y RUTA_ACTUAL/.claude/rules/usuarios-permisos.md.

Reutiliza: res.company, res.users, res.groups, ir.rule y el historial de mail. Evalúa si la
sucursal conviene como modelo propio o con algún módulo existente de sucursales, y justifica.

Crea solo lo que falte:
- Región (código, nombre, moneda, calendario de cobro: día de emisión y de vencimiento pospago,
  día de emisión prepago, días de gracia, hora de corte, prorrateo prepago y su fecha de inicio).
- Sucursal (región, nombre, dirección, teléfono), zona (región, nombre, sector o comunidad) y
  nodo (zona, coordenadas, capacidad instalada).
- Región en el usuario y un grupo por cada rol actual: superadmin, gerencia, admin_regional, noc,
  tecnico, finanzas, cajero, cobrador, almacenista, vendedor, operador_camaras, auditor, pasante.

Reglas que deben quedar probadas:
- Superadmin, gerencia y auditor ven todas las regiones; los demás, solo la suya.
- El auditor lee todo su alcance y no modifica nada.
- El pasante no ve clientes, cobros ni red.
- Nadie otorga un rol que no tiene. El administrador regional solo administra usuarios de su
  región y no crea usuarios sin región.
- Nadie cambia su propio rol ni su propio estado.
- Los usuarios se desactivan, no se borran. Los cambios de rol o de región quedan registrados.

Terminado cuando: las pruebas intentan romper el aislamiento (leer y escribir registros de otra
región por id) y no lo logran.
```

### Fase 2 — Clientes y planes

```text
Fase 2. Clientes y planes, dentro de mirabilenet_isp (o en un módulo mirabilenet_clientes si lo justificas).

Referencia: RUTA_ACTUAL/app/apps/crm/models.py y la clase Plan de RUTA_ACTUAL/app/apps/isp/models.py.

Reutiliza: res.partner para el cliente y sus contactos, crm.lead para los prospectos, product
(plantilla de producto de tipo servicio) para los planes y el módulo de contratos elegido en la
fase 0.

Agrega por herencia:
- En el cliente: código, región, zona, WhatsApp, tipo (residencial, empresarial, comunidad,
  institución, mina), estado comercial y datos fiscales (tipo y número de documento, complemento,
  razón social, correo).
- En el plan: velocidad de bajada y de subida en Mbps, si incluye TV, región (vacío: vale en
  todas), activo y «publicar en la web».

Reglas:
- «Activo» y «publicar en la web» son decisiones distintas. Un plan solo se publica si está
  activo, marcado para publicar y con precio mayor que cero. «Publicar» nace apagado.
- Un plan que usa algún servicio, aunque esté dado de baja, no se elimina: se desactiva.
- Un plan válido para todas las regiones solo lo elimina un usuario con alcance global.
- Solo gerencia y administración regional modifican planes.
- La modalidad de pago (prepago o pospago) NO va en el cliente: va en el servicio (fase 3).
```

### Fase 3 — Servicios y red

Es la fase más larga. Odoo no trae nada de esto.

```text
Fase 3. Módulo mirabilenet_isp: servicios y red.

Referencia: RUTA_ACTUAL/app/apps/isp/ completo (models.py, routeros.py, enrollment.py, subnets.py,
automation.py, wireguard.py y sus pruebas) y RUTA_ACTUAL/.claude/rules/isp-red.md.

Antes de programar, busca si existe algún módulo de la comunidad para proveedores de internet o
para RouterOS en la versión elegida. Si existe, evalúalo con honestidad; si está abandonado o es
de una versión antigua, descártalo y dilo.

Modelos a crear: servicio (cliente, plan, región, modalidad de pago, precio mensual, estado),
router, subred, cuenta PPPoE, código de enrolamiento de un solo uso, cambio de configuración del
router e historial de transiciones de estado del servicio.

Reglas:
- El direccionamiento depende del identificador de la región (10.<64+región>.x.0/24) y el
  asignador de subredes no puede producir solapamientos. Pruébalo.
- El código de enrolamiento sirve una sola vez y vence. El contenido del script que se genera
  para el router se cubre con pruebas.
- El servicio cambia de estado con acciones (activar, suspender, reactivar, dar de baja) y cada
  transición queda registrada.
- Las órdenes al router se ejecutan en segundo plano con reintentos (cola elegida en la fase 0),
  nunca dentro de la petición del usuario.
- El importador desde el router no adivina datos que el router no tiene.
- La comunicación con RouterOS no se probó contra equipos reales en el sistema actual: deja las
  llamadas detrás de una clase que se pueda reemplazar por un doble en las pruebas, y márcalo
  como pendiente de validar en laboratorio.

No copies claves ni configuraciones de WireGuard del sistema actual.
```

### Fase 4 — Cobros

```text
Fase 4. Módulo mirabilenet_cobros.

Referencia: RUTA_ACTUAL/app/apps/billing/ (models.py, services.py y pruebas),
RUTA_ACTUAL/.claude/rules/cobros.md y RUTA_ACTUAL/.claude/rules/modalidad-pago.md.

Decide y justifica una de estas dos bases, mostrándome qué se ahorra con cada una:
a) El aviso de cobro es una factura de cliente de Odoo (account.move) generada por el módulo de
   contratos, y el pago es account.payment.
b) El aviso de cobro es un modelo propio y Odoo solo se usa para caja y secuencias.
Ten en cuenta que hoy el sistema NO factura: emite avisos de cobro y recibos internos con la
leyenda «No constituye factura y no otorga crédito fiscal». Lo que elijas no puede presentarse
al cliente como una factura fiscal.

Reglas que deben quedar probadas:
- Ciclo por región, no por cliente. Prepago: el día configurado se emite el cargo del período
  actual, con vencimiento ese mismo día. Pospago: se cobra el período ya prestado, con su propio
  día de emisión y de vencimiento.
- Alta prepaga a mitad de mes: un cargo proporcional desde el día siguiente al alta hasta fin de
  mes, sobre los días reales del mes; el día del alta no se cobra y ese primer mes no lleva además
  el cargo completo. La fecha de inicio del prorrateo impide deuda retroactiva.
- La emisión es idempotente: volver a ejecutar la tarea del día no duplica cargos.
- Los pagos son idempotentes: un reintento no duplica el pago ni el recibo.
- Efectivo se aprueba al momento. Transferencia, QR y depósito quedan pendientes de conciliación
  y no generan recibo definitivo hasta aprobarse.
- Recibo interno con numeración correlativa sin huecos por sucursal y caja, también con usuarios
  simultáneos. Usa una secuencia sin huecos y demuéstralo con una prueba de concurrencia.
- Caja: apertura, cierre y arqueo. El cajero es el usuario de la sesión; no se elige ni se
  suplanta. Montos calculados y correlativos son de solo lectura.
- El pago aprobado es lo único que reactiva el servicio. Adjuntar un comprobante no reactiva.
- La deuda sale de los cargos emitidos y sus saldos, nunca del estado del servicio.
```

### Fase 5 — Inventario

```text
Fase 5. Inventario, con el módulo stock de Odoo.

Referencia: RUTA_ACTUAL/app/apps/inventory/models.py.

Objetivo: no programar. Instala stock y configura almacenes por región, productos, seguimiento
por número de serie y tipos de movimiento. Crea código propio solo para lo que stock no cubra, y
dime exactamente qué es antes de escribirlo.

Reglas: un almacenista regional solo ve los almacenes de su región; el auditor solo lee; los
movimientos no se borran, se revierten con otro movimiento.

Entrégame una lista de equivalencias: cada modelo y campo actual, y dónde queda en stock.
```

### Fase 6 — WhatsApp y asistente

```text
Fase 6. Módulo mirabilenet_whatsapp.

Referencia: RUTA_ACTUAL/app/apps/messaging/ completo, RUTA_ACTUAL/.claude/rules/mensajeria.md,
RUTA_ACTUAL/.claude/rules/seguimiento-mensajeria.md, RUTA_ACTUAL/INTEGRACION-WHATSAPP.md y
RUTA_ACTUAL/n8n-workflows/README.md.

Reutiliza si pasó la fase 0: la pasarela de WhatsApp de la comunidad para el envío, la recepción
y el hilo de mensajes. Lo demás se programa.

IMPORTANTE: los flujos de n8n (00 y 10 a 19) NO SE TOCAN. Funcionan y se conservan sin editar un
solo JSON. Odoo debe exponer la misma API que hoy usa n8n, en la misma dirección
(http://api:8000/api/v1/messaging/n8n/ dentro de la red de Docker), con las mismas rutas,
parámetros, respuestas y códigos de error:
- GET  /conversations/<id>/history, /charges, /proofs, /service, /plans, /sales, /organization,
  /retention-offers
- POST /conversations/<id>/lead, /handoff, /qr, /proofs/<comprobante>/charge
- POST /messages (respuesta del asistente), POST /ia/agotado, POST /alerts y GET /charges
Antes de programar, saca la lista real de rutas buscando «api/v1/messaging/n8n» en los JSON de
RUTA_ACTUAL/n8n-workflows/ y compárala con esta; si aparece otra, agrégala.
Odoo también envía al flujo 10 el mismo evento «mensaje_entrante», a la misma dirección del
webhook y con la misma firma (JWT HS256 de 2 minutos con el SHA-256 del cuerpo), y valida el
mismo token de la credencial «MIRABILENET API».
Copia el contrato exacto del README de n8n-workflows y de RUTA_ACTUAL/app/apps/messaging/n8n_api.py.

Terminado cuando:
- hay una prueba de contrato por ruta que compara los campos de la respuesta de Odoo con los del
  sistema actual, incluidos los rechazos 409 y su «codigo»;
- los flujos 13 a 17 responden bien desde el simulador contra Odoo;
- «git diff» sobre RUTA_ACTUAL/n8n-workflows/ no muestra ningún cambio.

Reglas que deben quedar probadas:
- n8n nunca tiene el token de Meta ni acceso a la base: solo usa esta API con su propio token.
- Todo mensaje que inicia la empresa sale por una plantilla aprobada por Meta.
- Ventana horaria de envío, tope diario por cliente, bajas (BAJA, STOP, CANCELAR, NO, SALIR),
  consentimiento y silencio cuando una persona atendió hace poco.
- Cada envío lleva una clave única: repetir la tarea no escribe dos veces.
- Las respuestas del asistente exigen la ventana de 24 horas de Meta, que no atienda una persona
  y que no haya baja; tope de 30 por hora.
- El mensaje entrante se registra antes de responder al webhook y se deduplica por el id de Meta.
- Comprobantes: adjuntar un archivo no registra un pago. La verificación la hace una persona,
  vinculando el comprobante a un cargo, en una caja activa de la región de ese cargo.
- El asistente solo responde con datos que devuelve esta API. La consulta de planes para
  interesados solo trae planes activos, publicados y con precio.
- Estilo editable del asistente, presentación de la empresa, promociones de retención, control de
  modelos y de cupo diario: los mismos ajustes que hoy, modificables solo con alcance global.
- Chats y solicitudes sin revisar se cuentan por región.
- El consentimiento nunca se crea en lote por inferencia.
```

### Fase 7 — Sitio web, cursos y pasantías

```text
Fase 7. Tres partes; hazlas en este orden y detente tras cada una.

A) Sitio web: módulos website y website_crm. Referencia: RUTA_ACTUAL/app/apps/web/ y
   RUTA_ACTUAL/.claude/rules/web-publica.md. Módulo propio mirabilenet_web solo para: localidades con
   cobertura (disponible, parcial, próximamente), planes publicados con la regla de la fase 2 y
   textos legales con versión y fecha de vigencia.
   Reglas: sin recursos de terceros (ni fuentes externas, ni CDN, ni analítica); lo que escribió
   el visitante en una consulta no se edita; convertir una consulta en prospecto es manual; solo
   gerencia y administración regional publican.

B) Cursos: evalúa website_event y website_slides contra RUTA_ACTUAL/app/apps/aerolab/models.py y
   elige el que cubra curso, cupo, fecha, precio e inscripción con menos código propio.
   Regla: un curso sin fecha, cupo o precio queda en preparación; esos datos no se inventan.

C) Pasantías: módulo project como base. Referencia: RUTA_ACTUAL/app/apps/pasantias/ y
   RUTA_ACTUAL/.claude/rules/pasantias.md. Módulo propio mirabilenet_pasantias para la pasantía, la
   lista de puntos de cada tarea, la entrega, la revisión y el informe de avance.
   Reglas: el pasante solo ve lo suyo; no se aprueba a sí mismo; no entrega si faltan puntos
   obligatorios y se le dice cuáles; no crea tareas ni se asigna trabajo; no borra un archivo ya
   aprobado; solo ve tareas publicadas; los adjuntos tienen lista de extensiones permitidas, que
   nunca incluye .html, .htm ni .svg, y un límite de 25 MB.
```

### Fase 8 — Indicadores

```text
Fase 8. Módulo mirabilenet_indicadores.

Referencia: RUTA_ACTUAL/app/apps/panel/ y el escritorio descrito en RUTA_ACTUAL/README.md.

Usa primero las vistas gráficas y de pivote que Odoo ya trae sobre los modelos de las fases
anteriores. Programa un tablero propio solo para lo que no salga de ahí.

Reglas: cada indicador respeta la región del usuario; un indicador sin datos muestra «—» y el
motivo, nunca 0; no se confunde cantidad de mensajes con monto adeudado; una notificación cuenta
como enviada solo si quedó en estado enviado, entregado o leído.
```

### Fase 9 — Migración de datos

```text
Fase 9. Migración de datos del sistema actual a Odoo.

Trabaja SOLO sobre una copia de la base de datos que yo te indique. No te conectes al servidor de
producción ni leas volcados por tu cuenta.

1. Escribe un guion de migración repetible, por etapas y en este orden: regiones, sucursales,
   zonas y nodos; usuarios; clientes y contactos; planes; routers y subredes; servicios y cuentas
   PPPoE; cargos, pagos, aplicaciones y recibos; inventario; conversaciones, mensajes,
   comprobantes y solicitudes; contenido web; pasantías.
2. Cada registro migrado guarda el identificador que tenía en el sistema anterior.
3. El guion se puede ejecutar dos veces sin duplicar nada.
4. Los recibos conservan su número original; la secuencia de cada caja continúa desde el último.
5. Las contraseñas no se migran: cada usuario define una nueva en su primer ingreso.
6. Informe de control por etapa: cantidad en el origen, cantidad migrada, rechazados con su
   motivo, y sumas de control (saldo total adeudado, total cobrado por mes, servicios por estado)
   iguales en los dos sistemas. Si una suma no coincide, no sigas: muéstrame la diferencia.
7. Nada se rellena con un valor por defecto para que «entre»: lo que no cumple una regla se
   reporta.
8. Los flujos de n8n no se tocan. Reciben los identificadores de conversación, mensaje, aviso y
   comprobante en cada evento, pero una lista de avisos enviada por WhatsApp antes del cambio
   lleva los identificadores viejos. Propón una de dos salidas y espera mi decisión: conservar
   los identificadores de avisos y comprobantes, o hacer el cambio sin listas pendientes de
   respuesta.
```

### Fase 10 — Puesta en marcha

```text
Fase 10. Puesta en marcha. No ejecutes nada contra el servidor de producción sin que yo lo
confirme paso por paso.

Prepara, sin ejecutarlo:
1. Un plan de operación en paralelo: qué se usa en cada sistema durante la transición y por
   cuánto tiempo, empezando por una sola región.
2. La lista de comprobaciones del día del cambio y el procedimiento para volver atrás.
3. El cambio del webhook de WhatsApp hacia Odoo y el paso de n8n a Odoo SIN editar los flujos:
   en la red de Docker, el nombre «api» en el puerto 8000 pasa a apuntar a Odoo, con el mismo
   token y el mismo secreto de firma. Volver atrás es devolver ese nombre al sistema anterior.
   Con su prueba previa en el simulador.
4. Respaldos de Odoo fuera del servidor, y cómo se restauran (prueba la restauración).
5. Manual de usuario actualizado para las pantallas de Odoo.
6. El Docker Compose del VPS: Odoo, PostgreSQL, la carpeta de addons propios y la de terceros.
   Es el primer uso de Docker en este proyecto (el desarrollo fue sin él). La clave
   MIRA_SIAT_MASTER_KEY entra como variable de entorno o secreto, nunca en la imagen ni en Git.
```

### Aparte — Facturación con el SIAT

Ya está decidido y construido: módulo propio `mira_sale_siat` (Compra y Venta, Telecomunicaciones y Nota de Crédito-Débito, Computarizada en Línea). El análisis anterior de `docs/PLAN-SIAT-MIRA-SALE.md` recomendaba un servicio aparte y quedó superado. Este prompt es para lo que falta.

```text
Facturación electrónica con el SIAT de Bolivia: terminar mira_sale_siat.

Lee custom_addons/mira_sale_siat/README.md, en especial «Pendiente antes de homologar». No
compares otros caminos ni busques módulos de terceros: la decisión está tomada.
1. Clave maestra MIRA_SIAT_MASTER_KEY definida en el servidor, fuera de Git y de la base.
2. Pruebas contra el ambiente PILOTO del SIN con el token y el código de sistema reales. Hasta
   ahora el módulo solo se probó contra su simulador: dime qué falla y qué pasa, sin suponer.
3. Confirmar con el SIN lo que el README marca como no verificado.
4. Enlazar la factura con los cobros de la fase 4: se emite al aprobarse el pago.
5. No reproduzcas de memoria formatos, catálogos ni servicios del SIN: se descargan de la fuente
   oficial antes de homologar.
Reglas fijas: la factura nunca bloquea el cobro ni la reactivación del servicio; la emisión es
idempotente; el recibo interno se mantiene; con la facturación apagada todo funciona como antes.
```

## 7. Control al final de cada fase

Antes de dar una fase por terminada, pregunta en la misma sesión:

```text
Antes de cerrar la fase:
1. ¿Qué módulos existentes reutilizaste y qué programaste? Dame las líneas de código propio.
2. Ejecuta todas las pruebas y pégame la salida completa.
3. ¿Qué regla de negocio de esta fase NO tiene prueba todavía?
4. ¿Qué dejaste sin hacer o sin verificar?
5. Confirma que los flujos de n8n siguen sin cambios (git diff sobre RUTA_ACTUAL/n8n-workflows/).
6. Actualiza ESTADO.md.
```
