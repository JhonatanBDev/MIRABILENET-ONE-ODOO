# Pendientes de configuración

Lo que falta para que el sistema funcione con datos y cuentas reales. El código está hecho y
probado con simuladores; nada de esto requiere programar, salvo donde se indica.

Actualizado el 23/11/2026. El estado del desarrollo está en `ESTADO.md`.

## 1. WhatsApp de Meta

Mientras no se configure, los mensajes quedan «por enviar» dentro de Odoo y nada llega a un
teléfono.

### 1.1 Cuenta y credenciales
En MIRABILENET > Mensajería > Ajustes:

- identificador de la cuenta de WhatsApp Business (WABA);
- ficha de acceso permanente (se guarda cifrada);
- secreto de la aplicación y ficha de verificación del webhook;
- encender «Mensajería activa» y apagar «Modo de prueba» cuando todo esté listo.

En MIRABILENET > Mensajería > Números: un número por sucursal, con su identificador de Meta.

En Meta, el webhook debe apuntar a `https://<dominio>/api/v1/messaging/whatsapp/webhook`, con
los campos de mensajes y de estados.

### 1.2 Plantillas que hay que crear y hacer aprobar en Meta
Idioma `es`. Las variables van en este orden, como `{{1}}`, `{{2}}`…. Los botones son de
respuesta rápida, en el orden indicado. El texto lo redacta la empresa.

**Nuevas, de lo último que se hizo (las tres que faltan sí o sí):**

| Plantilla | Para quién | Variables, en orden | Botones | Encabezado |
|---|---|---|---|---|
| `cotizacion` | Cliente | cliente, número de cotización, total | — | **Documento** (el PDF) |
| `cotizacion_revisar` | Vendedor | persona, número de cotización, cliente | — | — |
| `tarea_pasante` | Pasante | persona, tarea, fecha límite, enlace | Recibido | — |

Texto sugerido:
- `cotizacion`: «Hola {{1}}, te enviamos la cotización {{2}} por un total de {{3}}. Cualquier
  consulta, escríbenos por aquí.»
- `cotizacion_revisar`: «{{1}}, la cotización {{2}} para {{3}} quedó en borrador porque tiene
  alertas. Revísala en el sistema, apruébala y envíala.»
- `tarea_pasante`: «Hola {{1}}, tienes una tarea nueva: {{2}}. Fecha límite: {{3}}. Revisa la
  plataforma: {{4}}»

**Avisos al personal** (en el menú MIRABILENET, «Plantillas de avisos»):

| Plantilla | Variables, en orden | Botones |
|---|---|---|
| `averia_asignada` | persona, referencia, cliente, teléfono, dirección, caja, puerto, vecinos, mapa | Voy en camino, Arreglado, No se pudo |
| `averia_recordatorio` | persona, referencia, cliente, caja, horas | Voy en camino, Arreglado, No se pudo |
| `averia_resuelta` | persona, técnico, referencia, caja, pendientes de la caja, pendientes de la zona | — |
| `averia_no_resuelta` | persona, técnico, referencia, cliente, caja, nota | — |
| `averia_sin_atender` | persona, técnico, referencia, cliente, horas | — |
| `tarea_asignada` | persona, tarea, proyecto, fecha límite, asignado por | Recibido, Terminada |

**Avisos a clientes** (MIRABILENET > Mensajería > Plantillas; ahí se elige qué variables usa
cada una): `aviso_emitido`, `recordatorio_pago`, `aviso_vencido`, `recordatorio_mora`,
`comprobante_recibido`, `comprobante_verificado`, `comprobante_rechazado` y
`servicio_reparado`.

Si en Meta una plantilla queda con otro nombre, se cambia en Odoo en el campo «Nombre en
Meta»; la de cotización, en el parámetro `mirabilenet_cotizador.plantilla_cotizacion`.

### 1.3 QR de pago
Cargar el QR vigente de cada región en MIRABILENET > Mensajería > QR de pago. Sin él, el bot no
puede enviarlo.

## 2. Empresa en Odoo

- **Moneda y país:** la empresa sigue en dólares y con país Estados Unidos, así que las
  cotizaciones y los PDF salen con «$» / USD. Cambiar a Bolivia y bolivianos (BOB) en Ajustes >
  Empresas. Revisar antes el efecto en la contabilidad si ya hay asientos.
- **Datos y logo** de la empresa para los PDF.
- **Términos y condiciones** de ventas: hoy aparece el enlace que trae Odoo por defecto
  (Ventas > Configuración > Ajustes).

## 3. Cotizador de cámaras y redes

- **Credenciales de DigiCorp:** MIRABILENET > Cotizaciones > Configuración > Ajustes. La
  contraseña se guarda cifrada.
- **Conector de DigiCorp (falta programarlo):** trae productos, costos y existencias por
  ciudad. Sin él **el catálogo está vacío**: el bot no encuentra equipos y responde que un
  asesor confirma. Mientras tanto se pueden cargar productos a mano (pestaña «Cotizador» del
  producto).
- **Márgenes reales:** no están en GitHub. Se cargan en cada base con
  `documentacion\herramientas\cargar_margenes_cotizador.py` (necesita
  `referencia\config\pricing.yaml`, que tampoco está en GitHub) o a mano en Configuración >
  Recargos. El módulo trae solo un recargo de ejemplo.
- **Tarifas de mano de obra y viáticos:** las que trae son de ejemplo (Configuración > Mano de
  obra y Ciudades).
- **IVA:** confirmar si el precio de DigiCorp ya incluye IVA. Según eso, en Ajustes se elige
  «se suman al precio» o «ya están incluidos».
- **Qué ofrece el bot:** casilla «Ofrecer en el bot» en cada kit y en cada producto.
- **Quién cotiza:** dar el permiso «Cotizador: cotizar y enviar» a los usuarios que cotizan.

## 4. Personal

- Cargar al personal real con la plantilla (en el menú MIRABILENET, «Importar personal»): rol,
  región,
  **WhatsApp**, zonas y jefe. Sin WhatsApp no le llegan avisos.
- Asignar las zonas a los nodos, para que las averías vayan al técnico correcto.
- Queda un usuario de prueba desactivado, `e2e_tecnico`; no se usa.

## 5. Red y clientes

- **Routers:** probar las órdenes de red con un MikroTik de laboratorio antes de usarlas en
  la red real. Dar de alta los routers y el túnel de gestión.
- **Fibra:** completar los datos de campo de las cajas NAP y asignar a cada servicio su caja y
  su puerto. Revisar las cajas marcadas «por verificar».
- **Cartera de Yapacaní:** revisar `Static\Datos\datosyapacani_revisar_en_campo.csv` (no está
  en GitHub) y definir la fecha de inicio del cobro para crear los contratos.
- **Migración:** correr el guion de migración contra la copia real de la base anterior, con
  sus archivos.

## 6. Facturación electrónica (SIAT)

- Pedir a Impuestos las credenciales del ambiente piloto y cargarlas en el módulo fiscal.
- Pasar las etapas de prueba y obtener la autorización de producción.
- Recién entonces encender el puente con los cobros (viene apagado).

## 7. n8n

- En una PC nueva: crear las tres credenciales e importar los flujos (ver
  `INSTALAR_EN_OTRA_PC.md`, paso 9).
- La clave de Gemini es de una cuenta con cupo limitado; revisar el plan antes de producción.
- En el servidor, los flujos deben llamar a Odoo por la red interna (`http://odoo:8069`) y el
  parámetro `mirabilenet.n8n_inbound_webhook_url` debe apuntar al n8n del servidor.

## 8. Claves maestras

- Traer a cada PC las mismas `MIRABILENET_MASTER_KEY` y `MIRA_SIAT_MASTER_KEY` con que se
  cifraron los datos de su base. Está pendiente pasarlas de la PC original a la segunda PC.
- Guardar una copia fuera de las computadoras.

## 9. Servidor (producción)

- Contratar o preparar el servidor, el dominio y el certificado.
- Seguir `documentacion\puesta_en_marcha\` y `deploy\`: contenedores, variables de entorno,
  respaldos diarios y prueba de restauración.

## 10. Seguridad del repositorio

- El repositorio de código es público. En su historial quedó un archivo temporal de Word con
  el nombre del autor (commit `b4f271d`). Si se quiere borrar del todo, hay que reescribir el
  historial; después, cada PC debe volver a clonar.
