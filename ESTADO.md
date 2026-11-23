# ESTADO de la migración de MIRABILENET ONE a Odoo

Actualizado: 22/11/2026. Toda sesión de fase empieza leyendo este archivo.

Guía de fases: `documentacion/PROMPTS-MIGRACION-ODOO.md`.
Historial completo: `documentacion/historial_mirabilenet.md`.

## Para retomar (22/11/2026)

- **n8n traído de la otra PC y conectado a Odoo (23/11/2026):**
  - n8n 2.43.7 en Docker, en `C:\ING.SISTEMAS\n8n_local` (volumen `n8n_local`, puerto 5679),
    con los 10 flujos (9 activos) y las 5 credenciales.
  - Los flujos llaman a Odoo (`host.docker.internal:8069`) en vez de a `api:8000`. Las rutas
    `/api/v1/messaging/n8n/...` de `mirabilenet_whatsapp` son las mismas.
  - Los tokens están en las variables de entorno `MIRABILENET_N8N_API_TOKEN` y
    `MIRABILENET_N8N_WEBHOOK_SECRET`.
  - Parámetro `mirabilenet.n8n_inbound_webhook_url` = `http://127.0.0.1:5679/webhook/mirabilenet-entrante`.
  - Probado:
    - n8n → Odoo: 403 sin token y 200 con token; el flujo 00 ejecutado con éxito;
    - Odoo → n8n: el evento firmado se entrega y una firma falsa se rechaza.
  - Odoo tiene que arrancar con `--max-cron-threads 1` o más, porque los eventos salen por cron.
    Guía: `documentacion/n8n_local.md`.
  - **Seguridad:** la carpeta llegó por Google Drive sin cifrar. Borrarla de Drive y, si se
    compartió, rotar los tokens N8N y las claves de OpenAI y Gemini.
- **Dashboard 19.0.2.0.0 (23/11/2026, plan aprobado: limpiar + filtros + negocio + vistas por
  rol):**
  - Limpieza: quitados «Saldo vencido» y «Recibos de hoy» (repetidos), la segunda tarjeta de
    capacidad y el aviso de «recibos internos». Las altas salen por `date_start` del servicio.
    Las desincronizadas salen «—» sin router conectado.
  - Franja de alertas: routers caídos, comprobantes por revisar, vencidas de más de 30 días,
    NAP con 2 o más averías y MRR bajo el objetivo.
  - Filtros dinámicos: periodo (también Este mes, Mes pasado y fechas), región, zona, nodo,
    plan, modalidad y estado; chips con ✕ y «Limpiar»; clic en la dona o en un mes filtra el
    tablero; ▲▼ contra el periodo anterior. Se guardan por usuario en
    `res.users.settings.mirabilenet_dashboard_prefs`.
  - Negocio: MRR con objetivo, ARPU, churn, recaudación, altas y bajas de 6 meses,
    antigüedad de la cartera en 4 tramos, zonas con más mora y NAP con más averías.
  - Orden de secciones por rol y «Personalizar» para ocultarlas.
  - Sin filtro por sucursal: los servicios no la tienen.
  - 16 pruebas; revisado con Playwright en claro, oscuro, celular y en español.
  - Respaldo previo en `traslado_odoo/respaldo_antes_dashboard_v2`.
  - **Pendiente (bloque 4):** sesiones y tráfico desde RouterOS v7 por REST. Primero hay que
    confirmar la API en un router real.
- **Dashboard (22/11/2026, módulo nuevo `mirabilenet_dashboard` 19.0.1.0.0):** una pantalla OWL
  con todo el dashboard de MIRABILENET ONE: resumen, ingresos vs gastos, estado de servicios,
  actividad (auditoría), accesos rápidos, puesta en marcha (8 pasos), cobranza diaria y por
  método, clientes, cobros, red, capacidad, soporte, cartera vencida y últimos pagos.
  - Periodo Hoy/7/30/90 y región para usuarios globales; se actualiza solo cada minuto.
  - Cada número abre su lista con el mismo filtro (`action_open`).
  - Sin sudo (cada rol ve lo suyo; lo que no puede ver sale «—»).
  - Es la pantalla de inicio (hook + `ir.default`). Sigue el modo oscuro (variables de
    Odoo 19 sin prefijo `bs-`).
  - Sin datos todavía, con aviso: sesiones PPPoE en línea, tráfico, instalaciones con fecha y
    gastos (salen de facturas de proveedor).
  - 9 pruebas; instalado en `mira_nativo_test` y revisado con Playwright en claro, oscuro y
    celular. Respaldo previo en `traslado_odoo/respaldo_antes_dashboard`.
  - **Ojo:** la compañía de `mira_nativo_test` está en USD; las regiones, en BOB.
  - Usuario temporal `dashboard_tmp` archivado.
- **Tema visual moderno con los colores del logo (22/11/2026, noche, en la PC original):** nuevo
  módulo `mirabilenet_tema` 19.0.1.0.0 (parte interna: azul noche `#0f172a` en la barra, azul
  `#006db7` en acciones, celeste `#00abda` en modo oscuro, esquinas redondeadas, sombras
  suaves, ingreso como tarjeta). `mirabilenet_web` 19.0.2.1.0: paleta «mirabilenet» del sitio
  (primera en Editar > Tema > Colores) y botones redondeados, aplicada a los sitios existentes
  en `migrations/19.0.2.1.0/end-migrate.py` (en `post-migrate` falla: otros módulos del sitio
  todavía no están cargados). `mirabilenet_modo_oscuro` 19.0.1.0.1: enlaces del ingreso oscuro
  en celeste. 30 pruebas (tema, sitio, modo oscuro) en base limpia, 0 fallos. Instalado en
  `mira_nativo_test`; respaldo previo en `traslado_odoo/respaldo_antes_tema`. Ojo: los radios
  del sitio van en `rem` (con `px` el SCSS del sitio no compila). **Pendiente:** que el
  usuario lo vea en claro y oscuro y pida ajustes. **Base limpia en esta PC:** crearla antes
  con `LC_COLLATE 'C' LC_CTYPE 'C'` (si la crea Odoo, PostgreSQL 18 de Windows la rechaza).
- **Actualización tras el traslado (22/11/2026, PC original):** `-u all` en `mira_nativo_test`
  sin errores (184 módulos).

- **Sincronización con GitHub (22/11/2026):** el proyecto propio (sin Odoo, OCA, claves ni datos de
  clientes) va en un repositorio privado aparte, `odoo/.mirabilenet.git`, autor JhonatanBDev.
  Script `documentacion/herramientas/sincronizar_github.ps1` (estado / subir / bajar / instalar)
  y guía `documentacion/sincronizar_con_github.md`. Versiones de Odoo y OCA en
  `documentacion/versiones_odoo_y_oca.txt`. Bases, filestore y memoria para la PC original en
  `C:\ING.SISTEMAS\traslado_odoo\a_pc_original_22-11` (con LEEME). Subido a https://github.com/JhonatanBDev/MIRABILENET-ONE-ODOO
  (rama main). Falta: dejarlo privado y
  instalarlo en la PC original.
- **Cartera de Yapacaní importada en `mira_nativo_test`** desde
  `Static/Datos/datosyapacani_completo.csv`: 37 planes (uno por perfil de Winbox), 184 clientes,
  188 servicios activos prepago (Bs 25 000 al mes), 188 cuentas PPPoE con IP fija y perfil, 173
  ONU como números de serie en el cliente. Sin órdenes a routers ni contratos de cobro. Respaldo
  previo en `C:\ING.SISTEMAS	raslado_odoo
espaldo_antes_yapacani`. Herramientas y criterios:
  `documentacion/herramientas/importar_yapacani/`. **Pendiente:** revisar en campo
  `Static/Datos/datosyapacani_revisar_en_campo.csv` (83 avisos en 63 filas: MAC ilegibles o
  faltantes, ONU repetidas, C.I. faltantes o compartidos, fechas y coordenadas); decidir fecha
  de inicio del cobro para crear los contratos; asignar cada servicio a su caja NAP y puerto.
- **Sitio web editable con bloques dinámicos (22/11/2026, opción recomendada elegida por el
  usuario):** la prueba con Playwright mostró que los botones caían en la cabecera o el pie
  porque las secciones de MIRABILENET estaban hechas en código (bloqueadas, sin Style).
  `mirabilenet_web` 19.0.2.0.0: portada, Servicios, Planes, Cobertura, Proyectos y Preguntas
  son páginas editables (#wrap sin código); las listas son 8 bloques dinámicos nativos
  (grupo MIRABILENET del panel; filtros con acción de servidor; JS mínimo que resuelve el
  filtro por `data-mn-filter`). Probado en el editor real: el botón cae dentro de la portada,
  Style funciona en las secciones y en los bloques, un bloque arrastrado del grupo
  MIRABILENET muestra sus datos y queda tras guardar. 21 pruebas del sitio. **Pendiente:**
  `mira_nativo_test` no tiene contenido del sitio cargado (usar «Cargar contenido inicial» en
  MIRABILENET > Sitio web > Configuración y publicar planes); la excepción de Avast si el
  editor no abre en el navegador del usuario. Respaldo: `traslado_odoo/respaldo_antes_sitio_editable`.
  Generador de bloques y páginas: `documentacion/herramientas/generar_sitio.py`.
- **Importar otro día sin choques (22/11/2026, pedido del usuario):** probado con un caso de dos
  días. Antes, «Importar cartera» duplicaba al cliente que llegaba con C.I. el día 2, no completaba
  sus datos y le daba su IP a otro; los cambios se ignoraban sin aviso. Ahora reconoce al cliente
  por usuario PPPoE (o nombre y C.I.), completa lo vacío, lista lo distinto sin cambiarlo (opción
  «Reemplazar con los datos de esta planilla»), nunca cambia solo el plan ni la modalidad, detecta
  usuario PPPoE e IP repetidos en la planilla e IP de otro cliente. El importador de cajas NAP y
  tramos anota cada dato que reemplaza y tiene «Conservar los datos ya cargados». Cartera
  19.0.1.2.0 y fibra 19.0.1.2.0; 53 pruebas en base limpia. La planilla real de Yapacaní re-subida
  da 0 diferencias. Respaldo previo: `traslado_odoo/respaldo_antes_conciliar`.
- **Cajas NAP estandarizadas (22/11/2026, pedido del usuario):** cada caja nace con los puertos
  estándar de Ajustes > Red de fibra (8; botón «Aplicar a las cajas sin puertos»); las 112 cajas
  de Yapacaní pasaron a 8 puertos (896) con la migración `mirabilenet_fibra` 19.0.1.1.0. Cada
  puerto muestra la IP y el usuario PPPoE del servicio conectado (buscable por IP). Nuevo
  asistente **Red de fibra > Ubicar cliente (por IP)** (también botón «Ubicar» en el servicio y
  «Ubicar cliente» en la avería): con IP, PPPoE, nombre o C.I. muestra caja, puerto, referencia,
  «Cómo llegar» (Google Maps), ramal, OLT/PON, la tabla de puertos de la caja con IP y averías
  abiertas, y avisa «revise primero la caja» con 2 o más averías abiertas en la misma caja.
  44 pruebas de fibra y cartera en base limpia, 0 fallos. **Falta:** asignar cada servicio a su
  caja y puerto (datos que pasará el usuario). **Hecho:** el asistente «Importar cartera»
  (`mirabilenet_cartera` 19.0.1.1.0, ahora depende de `mirabilenet_fibra`) acepta las columnas
  CAJA NAP (código o nombre corto) y PUERTO, también para servicios ya importados; 15 pruebas.
  Probado con la planilla real más dos cajas (con rollback). Plantilla y LEEME actualizados. Respaldo previo: `traslado_odoo/respaldo_antes_puertos_nap`.
- **Nuevo módulo `mirabilenet_cartera` (22/11/2026, con visto bueno del usuario):** asistente
  MIRABILENET > Importar cartera (gerencia y administración regional de su región): sube la
  planilla con las columnas de `datosyapacani_completo.csv`, muestra un resumen sin guardar,
  crea planes que falten (uno por perfil de Winbox), clientes, servicios activos sin órdenes a
  routers ni contratos, PPPoE y ONU, y entrega la lista «revisar en campo». Limpieza en
  `cartera/limpieza.py` (Python puro). 8 pruebas en verde. Con la planilla real da lo mismo que
  la importación por script (188 servicios, 184 clientes, 173 ONU, 83 avisos). Plantillas con
  datos de ejemplo y `LEEME.txt` en `Static/plantillas/` (cartera, cajas NAP, tramos).
- **Calendario de cobro (22/11/2026, pedido del usuario):** prepago = mes calendario, aviso a
  todos el «día de emisión (prepago)» de la región (por defecto el 1), vence el «día de
  vencimiento (prepago)»; pospago = meses enteros desde el día del alta (alta el 3 de noviembre
  paga el 3 de cada mes) y vence ese mismo día; altas del 29 al 31 pasan al 28 en meses cortos.
  `mirabilenet_contratos` 19.0.1.1.0 (nuevo `models/contract_line.py`), `mirabilenet_isp`
  19.0.2.1.0 (`billing_day` calculado, «Día de cobro»). El contrato ahora empieza el día del alta
  (antes tomaba la fecha de creación; n8n la mostraba mal). 187 pruebas de los módulos de cobro
  en base limpia, 0 fallos. **Ojo:** en `mira_nativo_test` las pruebas de base/isp fallan al
  preparar porque la región Yapacaní usa `wg_region_id` 1; correr la batería en base limpia.
- **graphify:** hooks del proyecto corregidos (ruta de la PC anterior); grafo principal
  reemplazado por el de `custom_addons`. Actualizar con `graphify update custom_addons` y copiar
  los archivos de `custom_addons/graphify-out` a `graphify-out` (no usar `graphify update .`).
- **Documentos recuperados:** `cajas_nap.md`, `cambiar_icono_y_banner.md` y
  `trasladar_a_otra_pc.md` habían desaparecido (causa desconocida); se rehicieron desde las
  transcripciones de Claude Code con su tamaño exacto. La limpieza de `documentacion/` quedó
  pendiente de confirmar (candidato: `herramientas/crear_base_prueba.py`).

## Para retomar (21/11/2026, computadora nueva)

- **Traslado terminado:** misma ruta, PostgreSQL 19, Python 3.10, `env\` nuevo, bases
  `mira_nativo_test` y `odoo` restauradas, conversaciones y claude-mem recuperados. Claves
  maestras regeneradas (las anteriores quedan descartadas; nunca pegarlas en el chat).
- **Avast en esta PC** intercepta HTTPS saliente (pip ya resuelto con `env\pip.ini`; Odoo
  hacia SIAT y Meta va a fallar igual) **y filtra el tráfico local a 127.0.0.1:8069**.
- **Editor del sitio web roto: causa encontrada, arreglo a medias.**
  - Causa 1, Avast: corta a los ~20 s la respuesta de `render_public_asset` (catálogo de
    bloques, ~570 KB; llega 516 096 bytes y se corta). Por la IP de la PC (172.22.176.1) llega
    entera en 0,1 s. Sin ese catálogo el panel lateral del editor no se abre (queda de 3 px).
    **Pendiente del usuario:** en Avast > Configuración > General > Excepciones agregar
    `http://127.0.0.1:8069/*` y `http://localhost:8069/*`. No se tocó la configuración de Avast.
  - Causa 2, plantillas: todas las páginas de `mirabilenet_web` tenían `#wrap` como una sola
    `oe_structure` con contenido generado por el código. **Corregido:** `#wrap` ya no es zona
    editable y hay zonas con nombre `oe_structure_mn_<pagina>_<n>` entre secciones (27 zonas).
    Prueba nueva `test_editor_drops_blocks_into_named_zones`; 20 pruebas del sitio en verde.
  - **Sin confirmar:** en un Edge automático, aun por la IP sin Avast, el panel cargó 39 bloques
    pero no recibió la clase `o_builder_sidebar_open`. Siguiente paso: con la excepción de Avast
    puesta, probar el editor en el navegador real; si el panel sigue cerrado, registrar la red
    del editor por la IP (posible pedido del iframe a 127.0.0.1 por `web.base.url`).
- **Modo oscuro:** ver la entrada de abajo; el ingreso también es oscuro.
- **Mapa de fibra:** sin aviso «Map data not yet available» (satélite hasta zoom 17).
- **Usuario temporal `editor_tmp`** (pruebas del editor) en `mira_nativo_test`: borrarlo
  cuando el editor quede confirmado.
- Playwright MCP registrado en Claude Code (`claude mcp add playwright`, alcance usuario):
  disponible al reiniciar Claude Code.

## Para retomar (actualizado el 20/11/2026, cierre de la noche)

- **Hecho hoy:**
  - fase 8 completa, con la alerta de objetivo de MRR (`mirabilenet_indicadores`);
  - fase 9: el guion de migración completo, todas las etapas (`mirabilenet_migracion`),
    probado con tablas de prueba del esquema real;
  - la preparación de la fase 10 (`deploy/` y `documentacion/puesta_en_marcha/`), sin tocar el VPS;
  - **limpieza:** borrados `retirados/`, los repositorios de OCA sin uso (queue, server-tools,
    pos, project, web) y el módulo de paga simplifyit; quitado el código que no se usaba;
  - **estructura estándar Odoo/OCA** en los 13 módulos propios (`documentacion/estandar_modulos.md`):
    un archivo por modelo, vistas por modelo, menús aparte, `wizards/`, `readme/`, AGPL-3;
  - **nuevo módulo `mirabilenet_fibra`** (pedido en `documentacion/cajas_nap.md`): cajas NAP,
    puertos asignados al **servicio**, tramos, mapa con Leaflet de OCA
    (`oca/geospatial/web_leaflet_lib`, agregado a `odoo.conf` y a `deploy/odoo.conf.example`),
    averías en Mantenimiento, importación de CSV con correcciones deducidas y avisos
    «revisar en campo», importación de KML/KMZ, colores por ramal elegidos por nosotros.
- **Datos de fibra cargados en `mira_nativo_test`** (región nueva «Yapacaní»): los CSV de
  `Static/cvs naps/`: 112 NAP y 27 tramos, 115 correcciones deducidas, 6 para revisar en campo
  (YAP-B-04 ubicación; TR-24 y TR-26 longitud; TR-03, TR-05 y TR-06 arrancan en una reserva).
- **Decidido hoy por el usuario:** indicadores con `mis_builder` de OCA. Cambio de mensajería
  **sin listas pendientes**. La copia de la base para la fase 9 la pasa después. Las claves
  maestras se cambian más adelante. Fibra: puerto por servicio, averías en Mantenimiento,
  Leaflet de OCA, corregir lo deducible y marcar el resto.
- **Siguiente:**
  1. **el usuario prueba el mapa de fibra en el navegador** (nadie lo vio todavía en pantalla)
     y dice qué cambiar; dos colores parecidos: 7DE_2_EXT y 6DE_EXT;
  2. KML/KMZ de Google Earth para el recorrido real de los tramos;
  3. datos de campo: puertos por NAP (ninguna los tiene), OLT, zona, dirección, color del hilo,
     ocupación real, PON en 59 NAP, hilos y tipo de cable de los tramos;
  4. revisar todo lo demás en el navegador;
  5. correr la migración contra la copia que indique el usuario (con copias de `media` y
     `private_media`) y revisar el informe de control;
  6. ensayo en el VPS (documentación de puesta en marcha).
- En `mirabilenet-one/` hay un archivo `mirabilenet.dump`: **no se usó**. Solo se usa la copia
  que indique el usuario.
- **Regla de trabajo:** nativo primero, OCA después, propio solo si no existe y con visto bueno.
  SIAT propio. Todo módulo nuevo sigue `documentacion/estandar_modulos.md`.
- **Base de pruebas:** `mira_nativo_test` (comando abajo). Instalación limpia: **335 pruebas,
  0 fallos** (con `mirabilenet_fibra`). Tu base `odoo` no tiene los módulos de MIRABILENET.
- **Levantar Odoo para probar:**
  `env\Scripts\python.exe odoo-bin -c odoo.conf -d mira_nativo_test --db-filter "^mira_nativo_test$" --http-port 8069 --max-cron-threads 0`
  y abrir http://127.0.0.1:8069 (menú MIRABILENET > Mapa de fibra).
- Copias de los módulos antes de la reestructuración: carpeta temporal de la sesión
  (`scratchpad/backup`, `backup2`, `backup3`); pueden desaparecer.
- Nada está en git todavía.
- **Modo oscuro (21/11/2026):** OCA `web_dark_mode` 19.0 en `oca/web` (descargado solo ese módulo,
  con `git sparse-checkout`), agregado a `odoo.conf` y a `deploy/odoo.conf.example`, instalado en
  `mira_nativo_test` y `odoo` (9 pruebas en verde). Todos los usuarios internos y los nuevos
  siguen el modo del navegador o del sistema. Módulo propio nuevo **`mirabilenet_modo_oscuro`**
  (pedido por el usuario; depende solo de `web` y `web_dark_mode`, instalado en las dos bases,
  4 pruebas): guarda esa regla (`ir.default` y gancho de instalación) y oscurece la pantalla de
  ingreso, registro y cambio de contraseña. El resto del sitio público y el punto de venta
  siguen claros.
- **Mapa de fibra:** el satélite de Esri pide fotos hasta el zoom 17 (sobre Yapacaní no hay más;
  desde el 18 salía «Map data not yet available»).
- **Para mudarse a otra computadora:** `documentacion/trasladar_a_otra_pc.md`.
- **Traslado hecho el 21/11/2026** a la computadora nueva (misma ruta, PostgreSQL 19, Python 3.10):
  bases `mira_nativo_test` y `odoo` restauradas con sus filestores, `env\` creado, memoria de
  claude-mem y conversaciones recuperadas. Claves maestras `MIRABILENET_MASTER_KEY` y
  `MIRA_SIAT_MASTER_KEY` **regeneradas el 21/11/2026** (las viejas quedan descartadas; las bases
  no tenían secretos cifrados). Respaldarlas en el gestor de contraseñas. En esta PC Avast intercepta HTTPS: `env\pip.ini`
  ya apunta a su certificado; para otro Python usar `pip --cert "C:\ProgramData\Avast Software\Avast\wscert.pem"`.

## Decisiones fijas

- **Odoo Community 19.0**, con el código fuente en este repositorio. Módulos propios en
  `custom_addons/`, con prefijo `mirabilenet_` (el del SIAT se llama `mira_sale_siat`).
- **Desarrollo local sin Docker**: Windows, entorno virtual `env\`, PostgreSQL local, base `odoo`.
- **Docker Compose solo al final**, para desplegar en el VPS cuando la migración esté terminada
  (fase 10).
- **SIAT resuelto con módulo propio** (`mira_sale_siat`). No se evalúan otros caminos.
- **n8n no se toca.** Odoo se adapta a los flujos; nunca al revés.
- `custom_addons/simplifyit_l10n_bo_facturacion` es un módulo de paga (OPL-1) que se conserva solo
  como referencia de reglas: no se instala y no se copia su código.

## De dónde se migra

MIRABILENET ONE: Django 5 + DRF + Celery, PostgreSQL, Redis, Next.js 16 y n8n. Está en
`C:\ING.SISTEMAS\SISTEMAS_Y_PROYECTOS\mirabilenet-one` (rama `feature/whatsapp-release-ux`) y en
producción en el VPS. Esa carpeta es la `RUTA_ACTUAL` de los prompts: se lee, no se modifica.

## Cambio de rumbo (20/11/2026): módulos nativos primero

El usuario pidió usar y adaptar los módulos nativos de Odoo en lugar de crear módulos propios,
y corregirlo en todo el proyecto. Hecho hasta ahora:

- Instalados en `mira_nativo_test` y en `odoo`: `hr_attendance`, `sale_management`, `purchase`,
  `point_of_sale`, `project`, `mrp`, `maintenance` (traen `account`, `hr`, `stock`). En `odoo`
  además `crm`, `stock` y `website`. Los módulos propios siguen solo en `mira_nativo_test`.
- Con todo eso instalado la batería sigue en 347 pruebas, 0 fallos.
- El sitio web ya va sobre `website`.

**Decidido (20/11/2026): todo sobre lo nativo y OCA, incluido cobros. SIAT se queda como
módulo propio.** Orden: 1) cobros sobre `contract` (OCA) y facturas; 2) sucursales como puntos
de venta; 3) AeroLab sobre Eventos y pasantías sobre Proyecto; 4) indicadores con informes de
Odoo. Antes de programar cada paso se revisa si OCA tiene algo para la 19.

**Paso 1, hecho (20/11/2026).** Cobros sobre lo nativo:

- `mirabilenet_contratos`: servicio → contrato OCA (`contract` + `contract_variable_qty_prorated`,
  meses calendario con prorrateo) → factura de Odoo; corte, reactivación y región.
- `mirabilenet_contratos_siat`: factura fiscal al quedar pagada (interruptor en la empresa),
  con reintento y registro de quién cobró. `mira_sale_siat` no se tocó.
- `mirabilenet_whatsapp` pasó a facturas y pagos de Odoo; verificar un comprobante registra el
  pago. Los flujos de n8n no se tocaron: mismas rutas y campos.
- `mirabilenet_cobros` y `mirabilenet_cobros_siat` apartados en `retirados/`.

**La base de pruebas vigente es `mira_nativo_test`** (crearla con
`documentacion/herramientas/crear_base_nativo.py odoo.conf`). `mira_siat_test` quedó con los
módulos antiguos y ya no sirve. Batería completa allí, con las aplicaciones nativas instaladas:
301 pruebas entonces. Los recuentos y el comando de más abajo son anteriores a este cambio.

**Paso 2, hecho (20/11/2026).** `mirabilenet_pos`: cada sucursal es un punto de venta nativo;
vender un plan crea el servicio pendiente de instalación (la mensualidad no se cobra en caja,
la factura el contrato). OCA `pos` 19.0 descargado en `oca/pos`, sin módulos útiles; no
añadido a la ruta. Cobrar facturas desde el punto de venta es de Enterprise: en Community se
registra el pago desde la factura. `mirabilenet_base`: el administrador técnico cuenta como
alcance global. Batería: 305 pruebas entonces.

**Paso 3, hecho (20/11/2026).**

- `mirabilenet_aerolab` rehecho sobre Eventos (`website_event_sale`, entradas con precio y
  cobro por la tienda) y OCA `event_min_seat`. Se pierde la lista de espera y la edad mínima.
- `mirabilenet_pasantias` rehecho sobre Proyecto y Empleados (practicantes). Una tarea por
  pasante, subtareas como lista de puntos, informe de avance propio con PDF.
- Los módulos propios anteriores, en `retirados/`. OCA `event` y `project` 19.0 descargados en
  `oca/`; `oca/event` añadido a `addons_path` en `odoo.conf`.
- `mirabilenet_pos`: la sucursal usa una sola lista de precios.
- Instalación limpia de todo en `mira_nativo_test`: **294 pruebas, 0 fallos**.
- Lección: en Proyecto, las reglas de Odoo para usuarios internos dejan ver una tarea a quien
  la sigue. Para limitar al pasante hacen falta dos reglas: una global que recorta y una de
  grupo que concede.

**Paso 4, hecho (20/11/2026, tarde).** Indicadores: tableros nativos `spreadsheet_dashboard_*`,
informe mensual con OCA `mis_builder` (más `report_xlsx` y `date_range`; `oca/mis-builder`,
`oca/reporting-engine` y `oca/server-ux` en `addons_path`) y vistas nativas. Elegido por el
usuario frente a un módulo propio. Instalación limpia: **297 pruebas, 0 fallos**.

## Fases

| Fase | Qué | Estado |
|---|---|---|
| 0 | Entorno y comprobación de módulos | Hecha: los módulos de la OCA están descargados e instalan |
| 1 | Organización, usuarios y aislamiento por región (`mirabilenet_base`) | Hecha: 23 pruebas en verde |
| 2 | Clientes y planes (`mirabilenet_isp`) | Hecha: 18 pruebas en verde |
| 3 | Servicios y red (`mirabilenet_isp`) | Hecha con doble de router: 41 pruebas. Falta laboratorio con un MikroTik real |
| 4 | Cobros | **Rehecha sobre lo nativo** (`mirabilenet_contratos` + `mirabilenet_contratos_siat`: contrato OCA, factura y pago de Odoo, prorrateo, factura fiscal al cobrar) |
| 5 | Inventario (`mirabilenet_inventario` sobre `stock`) | Hecha: 13 pruebas |
| 6a | WhatsApp: avisos de cobro por plantilla (`mirabilenet_whatsapp`) | Hecha: 39 pruebas |
| 6b y 6c | WhatsApp: conversaciones, la API de n8n, comprobantes, solicitudes, asistente, promociones | Hechas contra dobles: 42 pruebas. Falta probar con n8n real |
| 7A | Sitio web público (`mirabilenet_web`) | Hecha sobre el módulo `website` de Odoo |
| 7B | Cursos AeroLab (`mirabilenet_aerolab`) | **Rehecha sobre Eventos** (`website_event_sale`, OCA `event_min_seat`) |
| 7C | Pasantías (`mirabilenet_pasantias`) | **Rehecha sobre Proyecto y Empleados** |
| 8 | Indicadores (`mirabilenet_indicadores`) | Hecha: tableros nativos, `mis_builder` (OCA), vistas nativas y alerta de objetivo de MRR. 4 pruebas |
| 9 | Migración de datos (`mirabilenet_migracion`) | Guion completo, todas las etapas de la guía, probado con tablas de prueba (8 pruebas). Falta correrlo contra la copia real con `media` y `private_media` |
| — | Red de fibra: cajas NAP, puertos, tramos y mapa (`mirabilenet_fibra`) | Hecho y probado (29 pruebas); CSV reales importados en la base de prueba. Falta verlo en el navegador, el KML/KMZ y los datos de campo |
| 10 | Puesta en marcha y Docker para el VPS | Preparada sin ejecutar: `deploy/` (Compose validado, nginx, respaldos) y `documentacion/puesta_en_marcha/`. Restauración probada en desarrollo |
| — | Sucursales como puntos de venta (`mirabilenet_pos`) | Hecha (paso 2 del cambio de rumbo) |
| SIAT | Facturación electrónica (`mira_sale_siat`) | Hecha contra el simulador; falta PILOTO |
| SIAT + cobros | Factura fiscal al quedar pagada (`mirabilenet_contratos_siat`) | Hecha: 2 pruebas. Apagada por defecto |

Todos los módulos juntos, instalación limpia en `mira_nativo_test`: **335 pruebas, 0 fallos**
(20/11/2026, con indicadores y migración). Los recuentos por fase de más abajo son anteriores al cambio de rumbo.

## Fase 0: módulos a reutilizar

Comprobado el 19/11/2026. Los tres repositorios de la OCA están clonados en `oca/` (rama 19.0) y
agregados a `addons_path` en `odoo.conf`. `contract`, `queue_job` y `auditlog` **instalan sin
errores** en la base de prueba; todavía no se usaron en ningún flujo, así que falta probarlos a
fondo en la fase que los necesite. `queue_job` pide la librería `openupgradelib`, ya instalada en
`env\`.

| Necesidad | Módulo | Origen | Licencia | Versión 19.0 | Veredicto provisional |
|---|---|---|---|---|---|
| Cobro recurrente | `contract` | OCA/contract | AGPL-3 | 19.0.1.5.0 | Instala; a probar a fondo en la fase 4 |
| Tareas en segundo plano con reintentos | `queue_job` | OCA/queue | LGPL-3 | 19.0.2.4.0 | Instala; a probar a fondo en la fase 3 |
| Auditoría de cambios | `auditlog` | OCA/server-tools | AGPL-3 | 19.0.2.0.2 | Instala; la fase 1 no lo necesitó (ver abajo) |
| WhatsApp (API de Meta) | `mail_gateway`, `mail_gateway_whatsapp` | OCA/social | AGPL-3 | **No publicados en 19.0** (sí en 18.0) | No sirve hoy: se programa en `mirabilenet_whatsapp` |
| Localización de Bolivia | `l10n_bo` | Odoo (`addons/`) | LGPL-3 | 2.0 | Viene con Odoo; plan de cuentas e impuestos |
| Facturación SIAT | `mira_sale_siat` | Propio | — | — | Hecho |
| CRM, proyectos, inventario, web, eventos, cursos | `crm`, `project`, `stock`, `website_crm`, `website_event`, `website_slides` | Odoo (`addons/`) | LGPL-3 | — | Presentes en `addons/` |

Qué cambia en el plan:

- **Fase 6 no se acorta.** Sin pasarela de WhatsApp para la 19.0, envío, recepción e hilo de
  mensajes se programan. Volver a mirar OCA/social al empezar esa fase por si ya se publicó.
- **`queue_job` quedó sin usar en la fase 3.** Las órdenes de red las ejecuta una tarea
  programada de Odoo que se dispara al instante (`ir.cron._trigger`), con los reintentos en la
  propia orden. Evita depender de un proceso aparte.
- **`contract` quedó sin usar.** En la fase 4 se eligió el aviso de cobro propio: el sistema no factura desde ahí, y el contrato del cliente es un modelo simple.
- **`auditlog` queda disponible pero sin usar.** La fase 1 lleva su propio registro inmutable
  (`mirabilenet.audit.log`), con región para respetar el aislamiento; `auditlog` sirve si se quiere
  registrar cualquier cambio de cualquier modelo desde la interfaz.
- **Licencias**: `contract` y `auditlog` son AGPL-3. Un módulo propio que dependa de ellos queda
  bajo AGPL-3. A tener en cuenta si alguna vez se distribuye el código.

## Módulos propios existentes

**`mirabilenet_base`** (`custom_addons/mirabilenet_base/README.md`)

- Regiones (con calendario de cobro y direccionamiento), sucursales, zonas y nodos.
- Rol, región y sucursal en el usuario; un grupo por rol; reglas de registro por región.
- Administración de usuarios con sus barreras y registro de auditoría inmutable.
- Los demás módulos `mirabilenet_*` dependen de él y reutilizan: el grupo
  `group_mirabilenet_user` (personal, sin pasantes), `group_mirabilenet_global`, el modelo
  abstracto `mirabilenet.region.scoped` y `mirabilenet.audit.log._log(...)`.
- Instalado solo en la base de prueba `mira_nativo_test`; **no** en la base `odoo`.

**`mirabilenet_isp`** (`custom_addons/mirabilenet_isp/README.md`)

- Clientes sobre `res.partner`: código, tipo, región, zona, sucursal, estado comercial con
  transiciones, contactos autorizados. Reglas de registro por región sobre `res.partner`.
- Planes sobre `product.template`: velocidades, región (vacío = todas), publicar en la web.
- Grupos nuevos: `group_mirabilenet_customer_manager` y `group_mirabilenet_plan_manager`.
- Red (fase 3): servicios, cuentas PPPoE, órdenes de red, routers con enrolamiento de un solo
  uso, subredes. La carpeta `isp/` no importa Odoo; `isp/gateway.py` es la única puerta a los
  equipos (`RealRouterGateway` / `FakeRouterGateway`).
- El cliente de RouterOS y las plantillas de enrolamiento se copiaron sin cambios del sistema
  anterior.
- Clave maestra propia para los secretos de red: variable de entorno `MIRABILENET_MASTER_KEY`.
- Grupos nuevos de la red: `group_mirabilenet_network_manager` y
  `group_mirabilenet_service_manager`.
- Puntos de enganche que la fase 4 debe usar: `mirabilenet.service._mirabilenet_on_activated`
  (prorrateo del alta prepaga) y `mirabilenet.service._request_transition(accion, key=...)`
  para cortes por mora y reactivación al pagar.
- Quedó para otras fases: contrato del cliente y saldo pendiente (fase 4), importador de
  cartera desde el router (fase 9), límite de intentos del punto público de enrolamiento y el
  servicio que aplica los peers de WireGuard (fase 10).
- Instalado solo en `mira_nativo_test`.

**`mirabilenet_cobros`** (`custom_addons/mirabilenet_cobros/README.md`)

- Avisos de cobro por región (prepago y pospago, con prorrateo del alta), pagos idempotentes,
  recibo interno con correlativo sin huecos, caja con arqueo, gastos y contratos.
- Reactivación al pagar y cortes por mora, a través de las órdenes de red de la fase 3.
- La carpeta `cobros/` no importa Odoo; todo se calcula en `Decimal`.
- Puntos de enganche para lo que sigue: `mirabilenet.charge._mirabilenet_notify(evento)`
  (WhatsApp, fase 6) y `mirabilenet.payment._mirabilenet_on_approved()` (factura SIAT).
- Diferencia con el sistema actual, decidida el 20/11/2026: el corte automático respeta los
  días de gracia de la región (antes nada los leía). Con 0 se comporta como antes.
- Instalado solo en `mira_nativo_test`.

**`mirabilenet_inventario`** (`custom_addons/mirabilenet_inventario/README.md`)

- Usa el inventario de Odoo (`stock`): almacenes, productos, series (`stock.lot`),
  existencias (`stock.quant`) y movimientos (`stock.move`).
- Solo se programó: la región del almacén y sus reglas, los nueve tipos de movimiento del
  sistema actual (`stock.move._mirabilenet_move`) y la situación de cada serie.
- El README trae la tabla de equivalencias campo por campo que pedía la fase.
- Los movimientos deben hacerse desde «Registrar movimiento»: hechos desde las pantallas
  estándar de Odoo no actualizan la situación de la serie.

**`mirabilenet_cobros_siat`** (`custom_addons/mirabilenet_cobros_siat/README.md`)

- Puente entre cobros y SIAT; ninguno de los dos depende del otro.
- Al aprobarse un pago lo deja «por facturar»; una tarea arma la factura de Odoo
  (`account.move`, una línea por aviso cobrado) y la entrega a `mira.siat.invoice._issue`.
- La factura nunca bloquea el cobro ni la reactivación. Apagado por defecto, por empresa.
- Las facturas quedan «por cobrar» en la contabilidad de Odoo: el cobro no se registra ahí.
- Anular un pago no anula sola la factura ante el SIN: deja un aviso.

**`mirabilenet_whatsapp`** (`custom_addons/mirabilenet_whatsapp/README.md`)

- Parte 6a: bandeja de salida de avisos de cobro por plantilla de Meta, con
  bajas, horario, tope diario, silencio por atención humana e idempotencia (el consentimiento
  por cliente no se exige: decisión del 20/11/2026, opción apagada en Ajustes); webhook de Meta
  para estados de entrega y bajas; QR de pago por región; envío manual.
- `whatsapp/gateway.py` es la única puerta a Meta (`RealMetaGateway` / `FakeMetaGateway`);
  `whatsapp/cloud_api.py` se copió sin cambios del sistema anterior.
- Se engancha en `mirabilenet.charge._mirabilenet_notify`; cobros no depende de este módulo.
- Partes 6b y 6c: conversaciones (`mirabilenet.conversation`), comprobantes, solicitudes de
  atención, alertas de n8n, ajustes del asistente, promociones de retención y la API de n8n
  (`mirabilenet.n8n.api` + `controllers/n8n_api.py`): las 22 rutas del sistema anterior, con el
  mismo contrato. Verificado que todas las rutas que llaman los JSON de n8n existen.
- Eventos a n8n firmados igual que antes (`whatsapp/n8n.py`). Secretos en el entorno:
  `MIRABILENET_N8N_API_TOKEN` y `MIRABILENET_N8N_WEBHOOK_SECRET`, con los mismos valores que
  hoy usa el sistema anterior.
- Depende de `crm`: las consultas del asistente de ventas son `crm.lead`.
- **Los flujos de n8n no se tocaron y siguen apuntando al sistema anterior.** El cambio es en
  la fase 10. Falta la prueba con n8n real (flujos 13 a 17 con el simulador contra Odoo).

**`mirabilenet_web`** (`custom_addons/mirabilenet_web/README.md`)

- **Decidido con el usuario (20/11/2026): el sitio va sobre el módulo `website` de Odoo**,
  para integrarse con tienda en línea y demás. Páginas QWeb sobre `website.layout`; estilo de
  Odoo. Ya no rige «sin recursos de terceros». AeroLab va igual.
- Consultas del formulario como `crm.lead`, con reglas de región; se ven junto a las del
  asistente de ventas en MIRABILENET > Sitio web > Consultas.
- Las localidades publicadas llegan al asistente de ventas por el gancho
  `mirabilenet.region._mirabilenet_coverage_localities` (definido en `mirabilenet_base`).
- Contenido de partida: botón «Cargar contenido inicial» en la configuración del sitio y de
  AeroLab (los textos genéricos del sistema anterior; no pisa lo escrito). Los datos reales
  se migran en la fase 9. La política de cookies debe nombrar
  `session_id` en lugar de `csrftoken`.

**`mirabilenet_aerolab`** (`custom_addons/mirabilenet_aerolab/README.md`)

- Cursos, cupos e inscripciones en `/aerolab`, sobre el Sitio web de Odoo, con modelos propios.
- El apartado nace apagado; se enciende en MIRABILENET > AeroLab > Configuración.

**`mirabilenet_pasantias`** (`custom_addons/mirabilenet_pasantias/README.md`)

- Modelos propios y no `project` (motivos en su README). Menú propio «Pasantías».
- Decidido con el usuario (20/11/2026): modelos propios, límite de 90 MB, sin aviso por WhatsApp
  al pasante, vista «Trabajo del equipo» incluida, informe PDF sencillo.

Batería completa al 20/11/2026: **347 pruebas, 0 fallos** (74 SIAT, 23 base, 60 clientes,
planes y red, 46 cobros, 13 inventario, 8 puente SIAT, 81 WhatsApp, 19 sitio web,
11 AeroLab, 12 pasantías). Verificada también con una
**instalación limpia** de todos los módulos en una base recién creada.

**`mira_sale_siat`** (`custom_addons/mira_sale_siat/README.md`)

- Emite Factura de Compra y Venta (sector 1), de Telecomunicaciones (22) y Nota de Crédito-Débito
  (24), en modalidad Computarizada en Línea, por SOAP directo al SIN.
- Incluye CUIS, CUFD, catálogos, contingencia, CAFC, fecha anterior, anulación, PDF, ticket y correo.
- 74 pruebas en verde contra el simulador. Nunca se probó contra PILOTO.

Su modelo `mira.siat.invoice` cubre el `FiscalDocument` de la app `billing`: se enlaza con los
cobros en la fase 4.

## Reglas que vienen del sistema actual

- Los datos no se inventan: los asistentes solo responden con lo que devuelve la API.
- La factura nunca bloquea un pago ni la reactivación del servicio.
- Importes en decimal, nunca en coma flotante.
- Aislamiento por región con reglas de registro, no solo ocultando menús.
- Pagos y envíos idempotentes.

## Lecciones de Odoo 19 en este equipo

- Odoo no logra crear la base de pruebas en Windows: se crea a mano con `template0` y orden `C`.
- No llamar `_register` ni `_order` a un método de un modelo: chocan con atributos de Odoo («can't adapt type 'method'», «'bool' object is not callable»). Pasó tres veces.
- **Nunca conceder un permiso por una bandera de contexto.** El contexto lo envía el cliente en cada llamada. El privilegio lo da `env.su` (código bajo `sudo()`); si hace falta distinguir, se exige `env.su` **y** la bandera. Se corrigió en `mira_sale_siat`, `mirabilenet_isp` y `mirabilenet_cobros`.
- Un método que recibe registros debe comprobar el acceso en **su** entorno (`registro.with_env(self.env).check_access(...)`), no en el del registro recibido, y devolver registros con `with_env(self.env)` para no filtrar privilegios.
- En las pruebas, `registry.cursor()` comparte una sola conexión: para probar concurrencia real hay que abrir conexiones propias con `psycopg2`.
- En Git Bash, `--test-tags /modulo` se convierte en una ruta de Windows: usar etiquetas sin barra.
- Las reglas de registro van en `noupdate="1"`: si se cambia una ya instalada, `-u` no la toca. En desarrollo, recrear la base de prueba; en producción hará falta un guion de actualización.
- Tres reglas por modelo cuando el usuario interno de Odoo ya puede leerlo (contactos, productos, inventario): una para `base.group_user` que solo deja ver lo que no tiene región, otra para el personal con su región y otra global. Con dos, el pasante ve lo de su región.
- Las pruebas contables de Odoo corren con un usuario que no es el del sistema: las protecciones aplican también ahí (usar `sudo()` solo para simular lo que hace el sistema).
- Recrear la base de prueba e instalar todo desde cero: `env\Scripts\python.exe documentacion\herramientas\crear_base_prueba.py odoo.conf` (borra y recrea solo `mira_nativo_test`) y luego `-i` con todos los módulos (unos 6 minutos).
- Las reglas de registro se evalúan antes de escribir: para impedir que alguien mueva un
  registro a otra región hay que volver a comprobar el acceso después del `write`
  (lo hace `mirabilenet.region.scoped`).
- Las búsquedas de campos calculados reciben los operadores `in` y `not in`.
- Si cambió el esquema de un módulo ya instalado, lanzar con `-u <módulo>`; si no, error 500.
- Odoo 19: `models.Constraint`, `<list>` en lugar de `<tree>`, `group_ids`.
- `fields.Datetime.now()` no tiene microsegundos: una clave de idempotencia hecha con la hora hace que dos acciones en el mismo segundo se tomen por la misma. Usar `uuid`.
- Una búsqueda de campo calculado que lee con SQL necesita `flush_model()` antes.
- Las pruebas por HTTP (`HttpCase`) no corren con `--no-http`: usar `--http-port 8079`.
- Un manifiesto sin `description` hace que Odoo lea el `README.md` como RST y llene el log de
  avisos por las tablas: poner siempre una `description` corta.
- Las reglas de registro sobre `res.partner` y `product.template` son por grupo: se suman (OR)
  entre los grupos del usuario. Por eso hay tres: usuario interno, personal y alcance global.
- Un campo calculado con inverso (como la contraseña PPPoE) conserva en la caché lo que se escribió: hay que invalidarlo si no debe quedar a la vista.
- No escribir guiones de Python largos dentro de un heredoc de Bash: se rompen con las comillas.
  Usar un archivo.

## Pendientes y avisos

- Nada de este repositorio está en un commit: `custom_addons/`, `documentacion/`, `AGENTS.md`,
  `ESTADO.md`, `retirados/`, `oca/` (son clones de Git: no se versionan dentro de este repo).
- `retirados/` guarda los módulos propios reemplazados (cobros, su puente SIAT, AeroLab y
  pasantías propios). Fuera de la ruta de módulos; solo para consulta.
- Perdido al pasar a lo nativo: aprobación de pagos por finanzas, numeración propia de recibos,
  día de emisión por región, lista de espera y edad mínima de AeroLab, una tarea para varios
  pasantes a la vez. Cobrar la mensualidad desde el punto de venta es de Enterprise.
- La factura fiscal automática al cobrar nace apagada (ficha de la empresa, pestaña
  MIRABILENET): probarla antes contra SIAT piloto.
- **Cambiar las dos claves maestras de este equipo antes de guardar secretos reales**: se pegaron
  en una conversación el 20/11/2026. Hoy no hay nada cifrado con ellas.
- Las dos claves maestras (`MIRA_SIAT_MASTER_KEY` y `MIRABILENET_MASTER_KEY`) están definidas
  en este equipo como variables de entorno del usuario de Windows. Qué son y cómo respaldarlas:
  `documentacion/claves_maestras.md`. **El VPS necesita las suyas** (fase 10).
- **La red no se probó contra un MikroTik real.** Requiere laboratorio antes de producción.
- SIAT: probar en PILOTO con credenciales reales, confirmar los datos pendientes con el SIN y
  homologar (detalle en el README del módulo).

## Cómo ejecutar

```powershell
# Lanzar Odoo (http://localhost:8069, base odoo)
env\Scripts\python.exe odoo-bin -c odoo.conf

# Base de pruebas desde cero e instalación de todo, con sus pruebas (unos 6 minutos)
env\Scripts\python.exe documentacion\herramientas\crear_base_nativo.py odoo.conf
env\Scripts\python.exe odoo-bin -c odoo.conf -d mira_nativo_test -i mira_sale_siat,mirabilenet_base,mirabilenet_isp,mirabilenet_contratos,mirabilenet_contratos_siat,mirabilenet_inventario,mirabilenet_whatsapp,mirabilenet_web,mirabilenet_aerolab,mirabilenet_pasantias,mirabilenet_pos,mirabilenet_indicadores,mirabilenet_migracion,mirabilenet_fibra,mirabilenet_cartera,mirabilenet_modo_oscuro,mirabilenet_dashboard,hr_attendance,sale_management,purchase,point_of_sale,project,mrp,maintenance --without-demo=all --test-tags mirabilenet,mira_siat --stop-after-init --http-port 8079

# Todas las pruebas sobre esa base ya creada (SIAT + MIRABILENET)
env\Scripts\python.exe odoo-bin -c odoo.conf -d mira_nativo_test -u mira_sale_siat,mirabilenet_base,mirabilenet_isp,mirabilenet_contratos,mirabilenet_contratos_siat,mirabilenet_inventario,mirabilenet_whatsapp,mirabilenet_web,mirabilenet_aerolab,mirabilenet_pasantias,mirabilenet_pos,mirabilenet_indicadores,mirabilenet_migracion --test-tags mirabilenet,mira_siat --stop-after-init --http-port 8079

# Pruebas del módulo SIAT
env\Scripts\python.exe odoo-bin -c odoo.conf -d mira_nativo_test -u mira_sale_siat --test-tags mira_siat --stop-after-init
```
