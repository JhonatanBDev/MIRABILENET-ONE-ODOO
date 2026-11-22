Fase 9. Lee una **copia** de la base de PostgreSQL del sistema anterior (Django) y crea lo
equivalente en Odoo. No existe un módulo nativo ni de OCA para esto: es un guion propio.

## Etapas, en orden

| Etapa | Origen | En Odoo |
|---|---|---|
| organization | `core_region`, `core_branch`, `core_zone`, `core_node` | regiones, sucursales, zonas, nodos |
| users | `core_user` | usuarios con su rol, región y sucursal |
| customers | `crm_customer`, `crm_customercontact` | clientes y sus contactos |
| plans | `isp_plan` | planes (productos) |
| network | `isp_router`, `isp_networksubnet` | routers y subredes |
| services | `isp_service`, `isp_pppoeaccount` | servicios y cuentas PPPoE |
| billing | `billing_charge`, `billing_payment`, `billing_paymentallocation`, `billing_receipt` | facturas publicadas y pagos conciliados tal como estaban aplicados |
| inventory | `inventory_warehouse`, `_inventoryitem`, `_inventoryserial`, `_inventorystock` | almacenes, artículos, series y existencias |
| messaging | números, plantillas, bajas, consentimientos, QR, conversaciones y mensajes, avisos enviados, comprobantes, solicitudes, promociones y ajustes | los modelos de `mirabilenet_whatsapp` |
| web | ajustes, ventajas, cifras, aliados, servicios, cobertura, proyectos, preguntas, textos legales y consultas | los modelos de `mirabilenet_web` y `crm.lead` |
| aerolab | `aerolab_dronecourse`, `aerolab_courseenrollment` | eventos con su entrada e inscripciones con el carnet |
| internships | pasantías, proyectos, tareas, asignaciones, puntos, informes, archivos y comentarios | empleados practicantes, proyectos, una tarea por asignación con subtareas, informe, adjuntos y mensajes |
| contracts | servicios activos, morosos y suspendidos | contrato de cobro desde `MIRABILENET_INICIO_COBRO` |

## Reglas que cumple

- **Cada registro guarda su identificador anterior** (`ir.model.data`, módulo `migracion`,
  nombre `<tabla>_<id>`).
- **Dos veces no duplica:** lo ya migrado se salta y se cuenta como «ya estaban».
- **Nada se rellena para que entre:** lo que no cumple una regla queda rechazado con su motivo:
  - región o cliente inexistente;
  - rol del portal de clientes;
  - aviso anulado, en borrador, en revisión o incobrable;
  - pago aplicado a un aviso que no pasó.
- **Contraseñas:**
  - Los usuarios no traen contraseña; cada uno define una nueva.
  - Las de API de los routers y las de PPPoE están cifradas con la clave del sistema anterior: no se leen y se reporta cuántas son.
- **Sumas de control:** tienen que dar igual en los dos sistemas:
  - saldo total adeudado;
  - total cobrado por mes, en hora de Bolivia;
  - servicios por estado;
  - unidades en almacenes;
  - comprobantes por estado.
- **Sin efectos secundarios:**
  - Migrar no manda órdenes a la red.
  - Un pago histórico no pide reactivar ni emite factura fiscal (solo bajo el sistema, con la marca de migración).
  - El aviso de cobro original queda en la referencia de la factura y el número de recibo en la del pago.

## Decidido (20/11/2026)

- **Avisos y comprobantes de WhatsApp:** cambio sin listas pendientes de respuesta. El día del
  cambio se espera a que no haya listas de avisos ni comprobantes sin contestar; no se
  conservan los identificadores viejos.
