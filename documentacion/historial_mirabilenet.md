# Historial de desarrollo de MIRABILENET

Actualizado al 19/11/2026.

## 1. Mapa general

Hay dos líneas de trabajo:

| Línea | Carpeta | Tecnología | Estado |
|---|---|---|---|
| **MIRABILENET ONE** (gestión del ISP) | `SISTEMAS_Y_PROYECTOS\mirabilenet-one` | Django 5 + DRF + Celery, PostgreSQL, Redis, Next.js 16, n8n, Docker | En producción en el VPS |
| **Facturación SIAT en Odoo** | `SISTEMAS_Y_PROYECTOS\odoo\custom_addons\mira_sale_siat` | Odoo 19, SOAP directo al SIN | Funciona contra el simulador; falta PILOTO |

## 2. Línea de tiempo

**MIRABILENET ONE**

| Fecha | Hito |
|---|---|
| 02/10 | Código inicial (`4cdbcd8`). Apps: core, crm, isp, billing, inventory, messaging, panel, pasantías, web, aerolab |
| 13/10 | v1.1 |
| 18–22/10 | Automatización local de WhatsApp con n8n; corrección de plantillas de Meta y del bloqueo al revisar comprobantes en PostgreSQL |
| 28/10 | Bot de WhatsApp fases 1–3: n8n conectado a Django, conversaciones, simulador, alertas, webhook con JWT, comprobantes de pago por chat |
| 03–04/11 | Chats entrantes, respuestas con imagen y PDF, importación de cartera de servicios |
| 17–18/11 | Fase 4: agente de soporte con IA (workflow 15), ruta de entrada (10), derivación a persona (16). Cambio de OpenAI a **Gemini gratuito** por los recursos del VPS. Verificador que bloquea cifras que no vienen de la base |
| 18/11 | Bot de ventas; interruptores, modelo y cupo diario desde el panel; remitente compartido; **ciclo de cobro prepago/pospago por región**; script de despliegue con respaldo; **despliegue al VPS** y publicación de los 9 workflows |
| 18/11 (noche) | Arreglo del QR regional (error 500); aviso al cliente del resultado del comprobante, también fuera de la ventana de 24 h; estilo del bot editable, retención ante bajas y promociones; el bot muestra planes; se quitó el botón «Necesito ayuda» |
| 19/11 (madrugada) | Eliminar planes y control de roles en su API; el bot usa zonas, regiones y sucursales de Organización; «Quiénes somos» editable; el bot de ventas ya no dice «registré tus datos» sin registrarlos; bolita amarilla de pendientes (`4cbfac7`) |

**Documentos y decisiones**

| Fecha | Hito |
|---|---|
| 18/11 | Se leyó el PDF *Mira_Sale – Proyecto técnico SIAT Proveedor* y se escribió `docs/PLAN-SIAT-MIRA-SALE.md` (recomendaba un servicio aparte conectado por API) |
| 18–19/11 | Tesis: arquitectura con RUP, UML y vistas 4+1; luego adaptada al formato UPEA, con el SIAT como implementación futura (`docs/tesis/`) |
| 19/11 | `docs/PROMPTS-MIGRACION-ODOO.md`: migración de ONE a Odoo Community en 11 fases, prefijo `mirabilenet_`. Las automatizaciones de n8n no se tocan |

**Facturación SIAT en Odoo (19/11)**

1. Se instaló graphify en el repo de Odoo y se construyó el grafo de `custom_addons`; las reglas pasaron de `CLAUDE.md` a `AGENTS.md`.
2. Se creó `mira_sale_siat` a partir del PDF: Factura de Compra y Venta, Computarizada en Línea.
3. Se agregaron icono y banner, y la guía `documentacion/cambiar_icono_y_banner.md`.
4. Se leyó el módulo de paga `simplifyit_l10n_bo_facturacion` y se igualaron sus funciones **reescribiendo desde cero** (es OPL-1, no se copió código), en 11 fases.
5. Se lanzó Odoo con el módulo actualizado en la base `odoo`.

## 3. Lo logrado

**MIRABILENET ONE** (en GitHub, rama `feature/whatsapp-release-ux`)

- Gestión de clientes, servicios, routers, cobros y caja, inventario, web pública.
- Bots de WhatsApp de soporte y de ventas con IA, que responden solo con datos de la base.
- Verificación de comprobantes QR con aviso al cliente.
- Ciclo de cobro prepago y pospago por región.
- Panel de mensajería: chats, solicitudes, simulador, control del bot.
- Despliegue con respaldo previo. 571 pruebas (cifra registrada el 19/11).

**`mira_sale_siat`** (74 pruebas en verde contra el simulador)

- Documentos: Compra y Venta (sector 1), **Telecomunicaciones (22)**, Nota de Crédito-Débito (24).
- Adaptador `siat/` sin dependencias de Odoo: CUF, XML por sector, validación XSD, SOAP, empaquetado, bóveda cifrada, pasarela real y simulador.
- CUIS, CUFD, catálogos, numeración atómica, idempotencia, anulación y reversión.
- Contingencia con paquetes, talonarios CAFC, emisión con fecha anterior (máx. 48 h).
- NIT reservados 99001/99002/99003, validación de NIT, método de pago deducido de los cobros, gift card, descuento global, multimoneda, tarjeta enmascarada.
- Registro de puntos de venta ante el SIN, asistente de configuración, PDF con QR, ticket de 80 mm, correo al cliente.
- Roles (emisor, supervisor, administrador, fecha anterior), aislamiento por empresa, auditoría.

## 4. Problemas resueltos

**MIRABILENET ONE**

| Problema | Solución |
|---|---|
| El VPS no aguantaba OpenAI de pago | Gemini gratuito, con modelo de respaldo y cupo diario visible |
| El bot inventó cifras (35 y 140) | Verificador que bloquea datos sin respaldo en Django y alerta |
| El bot «dejó de responder» al cerrar el túnel | Se aclaró que n8n del VPS no depende del túnel local |
| Pantalla de QR regionales con error 500 | Corregida (`2fd72de`) |
| El cliente no sabía el resultado de su comprobante | Aviso por chat, y por plantilla si pasó la ventana de 24 h |
| El bot de ventas decía haber registrado al interesado sin hacerlo | Corregido (`c45377d`) |
| La API de planes se podía usar sin el rol debido | Control de roles (`785be53`) |
| nginx apuntaba al panel viejo tras desplegar | El script reinicia nginx |
| Permisos al importar workflows en n8n | Los archivos se entregan al usuario `node` |
| El bot no reconocía zonas ni regiones | Lee Organización; se quitó «en Oruro» fijo |

**`mira_sale_siat`**

| Problema | Solución |
|---|---|
| El PDF del plan no se podía leer | Se leyó con PyMuPDF |
| Odoo no creaba la base de pruebas en Windows | Base `mira_siat_test` creada a mano con `template0` y orden `C` |
| Un método `_register` chocaba con un atributo de Odoo | Renombrado a `_register_with_sin` |
| Odoo 19 envía el operador `in` a las búsquedas | Las búsquedas calculadas aceptan `in` / `not in` |
| Autorización cerrada en el mismo segundo violaba la restricción | Se permite inicio = fin |
| Error 500 al lanzar Odoo (faltaba una columna) | La base tenía la versión vieja; se relanzó con `-u mira_sale_siat` |
| Guía guardada dentro del módulo | Movida a la carpeta global `documentacion/` |

## 5. Lo que falta

**`mira_sale_siat`**

1. Definir `MIRA_SIAT_MASTER_KEY` en el servidor y reiniciar Odoo. Sin ella no se guardan token, CUIS ni CUFD.
2. Probar contra **PILOTO** con el token y el código de sistema reales: hasta hoy solo se probó con el simulador.
3. Confirmar con el SIN: el vector de prueba del CUF, `tipoFacturaDocumento = 3` en la nota, el código 986 de NIT activo y los plazos de eventos con fecha pasada.
4. Volver a descargar XSD, WSDL y catálogos antes de homologar (los XSD incluidos son del 23/08/2021).
5. Homologación ante el SIN (90 días más 60 de prórroga) y paso a producción.
6. Fuera de alcance por ahora: Electrónica en Línea (firma), API REST propia, módulo de abonados ISP en Odoo, notas sobre facturas en moneda extranjera, traducción `es_BO`.
7. Nada del repo de Odoo está en un commit: `custom_addons/`, `documentacion/`, `AGENTS.md` siguen sin versionar.

**MIRABILENET ONE**

1. Sin commit: `docs/PLAN-SIAT-MIRA-SALE.md`, `docs/PROMPTS-MIGRACION-ODOO.md`, `docs/tesis/`, y cambios en `CLAUDE.md` y en el workflow 16.
2. Despliegue de los últimos commits del 19/11 al VPS: último estado registrado, pendiente de confirmar.
3. Tesis: secciones marcadas «[A completar por el autor]».
4. Migración a Odoo: solo existe el documento de fases; no se empezó.
5. Conectar los cobros de ONE con la factura SIAT.

## 6. Decisiones que conviene recordar

- **Cambio de rumbo en el SIAT**: el plan del 18/11 recomendaba Mira_Sale como servicio aparte en Django; el 19/11 se construyó como módulo de Odoo. El documento `PLAN-SIAT-MIRA-SALE.md` ya no describe lo que existe.
- La tesis nombra solo el caso **S.I.E.T.E. S.R.L.**; no menciona MIRABILENET, Mira_Sale, AeroLab ni Oruro.
- MirabileNet emite Factura de Telecomunicaciones, solo en Computarizada en Línea.
- Solo `mira_sale_siat` queda instalado; el módulo de paga es referencia de reglas, no de código.
- Una factura nunca debe bloquear un pago ni la reactivación del servicio.
- Los bots nunca inventan datos; lo que no está en la base no se responde.
- n8n funciona bien y no se toca en la migración a Odoo.
- Importes en decimal, nunca en coma flotante; catálogos del SIN sincronizados, no escritos a mano.

## 7. Dónde está cada cosa

| Qué | Dónde |
|---|---|
| Plan técnico SIAT original | `C:\Users\Usuario\Desktop\Mira_Sale_Proyecto_Tecnico_SIAT_Proveedor.pdf` |
| Módulo SIAT y su README | `odoo\custom_addons\mira_sale_siat\` |
| Apuntes | `odoo\documentacion\` |
| Estado de la migración a Odoo | `odoo\ESTADO.md` |
| Guía de migración a Odoo (copia al día) | `odoo\documentacion\PROMPTS-MIGRACION-ODOO.md` |
| Plan SIAT anterior, copia vieja de la guía, tesis, manuales | `mirabilenet-one\docs\` |
| Workflows del bot | `mirabilenet-one\n8n-workflows\` |
| Odoo local | `http://localhost:8069`, base `odoo`; pruebas en la base `mira_siat_test` |
| Lanzar Odoo | `env\Scripts\python.exe odoo-bin -c odoo.conf` |
| Pruebas del módulo | `odoo-bin -c odoo.conf -d mira_siat_test -u mira_sale_siat --test-tags mira_siat --stop-after-init` |

## 8. Sesión del 20/11/2026: migración a Odoo 19 y cambio a lo nativo

**Hecho en el día (fases 1 a 7 de la guía):** organización y regiones, clientes, planes, red
(MikroTik con doble de pruebas), cobros, inventario, WhatsApp con la API de n8n (los flujos no
se tocaron), sitio web, cursos y pasantías.

**Cambio de rumbo, pedido por el usuario:** usar los módulos nativos de Odoo y adaptarlos, con
OCA como segunda opción, para ahorrar código y que el sistema no sea pesado. SIAT se queda como
módulo propio. Se instalaron Ventas, Compras, Punto de venta, Proyecto, Fabricación,
Mantenimiento y Asistencias. Resultado:

| Antes (propio) | Ahora |
|---|---|
| Sitio con plantillas propias | Módulo `website` de Odoo |
| `mirabilenet_cobros` (avisos, pagos, recibos, caja) | `mirabilenet_contratos`: contrato OCA + factura y pago de Odoo, prorrateo OCA |
| `mirabilenet_cobros_siat` | `mirabilenet_contratos_siat`: factura fiscal al quedar pagada, con reintento |
| — | `mirabilenet_pos`: cada sucursal es un punto de venta; vender un plan solicita el servicio |
| AeroLab propio | Eventos (`website_event_sale`) + OCA `event_min_seat` |
| Pasantías propias | Proyecto y Empleados |

**Decisiones del usuario en el día:** consentimiento de WhatsApp apagado; días de gracia en el
corte; sitio sobre `website` con estilo de Odoo; verificar un comprobante registra el pago a
nombre de quien verifica; la factura SIAT se emite al registrarse el pago; prorrateo con OCA;
pasantías con límite de 90 MB, «Trabajo del equipo», sin aviso por WhatsApp y PDF sencillo.

**Lecciones:** las reglas de Odoo para usuarios internos dejan ver una tarea a quien la sigue
(hace falta regla global + regla de grupo); las etapas creadas por datos deben llevar
`user_id` vacío o quedan como personales; una lista de precios de datos debe ir sin empresa;
el administrador técnico debe contar como alcance global.

**Estado al cerrar:** 294 pruebas, 0 fallos en una base limpia (`mira_nativo_test`). Nada
revisado en el navegador. Siguiente: fase 8, indicadores, con informes de Odoo.

**Tarde del 20/11/2026: fase 8, indicadores.** Se recuperó el historial (claude-mem y
`ESTADO.md`), se corrigieron dos errores del estado y se hicieron los indicadores con lo nativo:
tableros `spreadsheet_dashboard_*` de Odoo, informe mensual con `mis_builder` de OCA (elegido por
el usuario) y vistas nativas de gráfico y tabla dinámica, en `mirabilenet_indicadores`, un
módulo solo de datos. Lección: `mis_builder` filtra cada consulta por las fechas del período,
así que lo «a hoy» (MRR, mora) va en vistas nativas. Instalación limpia: 297 pruebas, 0 fallos.
Pendiente: alerta de objetivo de MRR por región; revisar todo en el navegador; fase 9.

**Noche del 20/11/2026: alerta de MRR, guion de migración y puesta en marcha.**

- Alerta de objetivo de MRR por región en `mirabilenet_indicadores`.
- Fase 9: `mirabilenet_migracion`, un guion por etapas, repetible, con identificador anterior y sumas de control que detienen todo si no coinciden. Probado con tablas de prueba del esquema real del sistema anterior (mapeado desde su código, sin abrir el volcado `mirabilenet.dump`).
- Fase 10, preparada sin ejecutar:
  - Docker Compose del VPS con la imagen oficial de Odoo 19, validado con `docker compose config`;
  - el cambio de nombre `api` para n8n sin editar flujos;
  - nginx, respaldos (restauración probada en desarrollo), operación en paralelo, día del cambio con vuelta atrás y manual de usuario.
- Decisiones del usuario: cambio de mensajería sin listas pendientes; copia de la base después; claves maestras más adelante.

**Etapas restantes de la migración (20/11/2026, noche).** Inventario, mensajería, contenido web,
AeroLab y pasantías, con sus controles: unidades en almacenes y comprobantes por estado. Los
archivos se leen de copias de `media` y `private_media`. Las fechas con zona del origen se pasan
a UTC sin zona. Los controles solo revisan las etapas que corrieron. 8 pruebas de la migración.

**Limpieza, estructura estándar y red de fibra (20/11/2026, noche).** Se borraron `retirados/`,
los repositorios de OCA sin uso (queue, server-tools, pos, project, web) y el módulo de paga
simplifyit. Los 13 módulos propios pasaron a la estructura de Odoo/OCA
(`documentacion/estandar_modulos.md`) y se quitó el código sin uso. Nuevo módulo
`mirabilenet_fibra`: cajas NAP, puertos asignados al servicio, tramos, mapa con Leaflet de OCA
(`oca/geospatial/web_leaflet_lib`), averías en Mantenimiento, importación de CSV con
correcciones deducidas y avisos «revisar en campo», importación de KML/KMZ. Importación real:
112 NAP y 27 tramos, 115 correcciones deducidas, 6 para revisar en campo. Instalación limpia y
regresión: 335 pruebas, 0 fallos.
