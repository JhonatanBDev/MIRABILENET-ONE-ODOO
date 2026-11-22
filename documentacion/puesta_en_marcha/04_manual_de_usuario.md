# Manual de usuario en Odoo

Fase 10, punto 5. Para el personal que usaba el panel del sistema anterior. Odoo se abre en
`https://<dominio>/odoo`. Cada persona ve solo su región; gerencia ve todas.

## Lo que cambió de lugar

| Antes (panel) | Ahora (Odoo) |
|---|---|
| Clientes | MIRABILENET > Clientes |
| Servicios y cuentas PPPoE | MIRABILENET > Servicios / Red |
| Avisos de cobro | MIRABILENET > Cobros > Facturas a clientes |
| Registrar pago y recibo | Abrir la factura > **Registrar pago** |
| Caja de sucursal | Aplicación **Punto de venta** (una caja por sucursal) |
| Aprobación de pagos | Ya no existe: el pago se registra directamente; el control es el cierre de caja |
| Comprobantes por WhatsApp | MIRABILENET > Mensajería > Comprobantes > **Verificar y registrar pago** |
| Conversaciones | MIRABILENET > Mensajería > Chats |
| Inventario | Aplicación **Inventario** |
| Indicadores | MIRABILENET > Indicadores |
| Sitio web y consultas | Aplicación **Sitio web**; consultas en MIRABILENET > Sitio web > Consultas |
| AeroLab | Aplicación **Eventos** |
| Pasantías | Aplicación **Pasantías** |

## Por rol

### Cajero y cobrador

1. **Cobrar una mensualidad:** MIRABILENET > Cobros > Facturas a clientes, buscar al cliente,
   abrir la factura vencida, **Registrar pago**, elegir el diario (caja o banco) y el monto.
   Si paga todo lo que debía y estaba cortado, el servicio se reactiva solo.
2. **Cliente nuevo en la sucursal:** Punto de venta > abrir la caja > elegir o crear el
   cliente > agregar el plan y la «Instalación del servicio» con el monto cotizado > cobrar.
   El servicio queda pendiente de instalación para el técnico.
3. **Comprobante por WhatsApp:** abrir el comprobante, revisar la imagen y la factura asociada,
   **Verificar y registrar pago** o **Rechazar** con el motivo. Al cliente le llega la respuesta.
4. **Cierre:** en el Punto de venta, cerrar la sesión de caja y contar el efectivo.

### Vendedor

- **Consultas del sitio:** MIRABILENET > Sitio web > Consultas. Marcar contactado o
  **Convertir en prospecto**. Lo que escribió la persona no se edita; se usa la nota interna.
- **Inscripciones a cursos:** Eventos > el curso > Asistentes.

### Técnico y NOC

- **Servicios:** abrir el servicio y usar los botones (activar, suspender, corte parcial,
  cambiar plan, baja). El estado cambia cuando el router confirma; si falla, la orden queda en
  revisión manual (MIRABILENET > Órdenes de red).
- **Routers:** MIRABILENET > Red > Routers. Un router nuevo se enrola con el guion que da Odoo.

### Finanzas y gerencia

- **Indicadores:** MIRABILENET > Indicadores:
  - cobranza y servicios por mes (exporta a Excel);
  - mora de más de 30 días;
  - objetivo de MRR por región;
  - tableros de Odoo.
- **Contratos de cobro:** MIRABILENET > Cobros > Contratos de cobro. Se crean solos al activar
  un servicio; el precio sigue al del servicio.
- **Factura fiscal SIAT:** ficha de la empresa > pestaña MIRABILENET > «Emitir la factura
  fiscal al registrar el pago».

### Tutor y pasante

- **Tutor:** Pasantías > Proyectos y Tareas. Una tarea por pasante, con subtareas como lista de
  puntos; marcar «Publicada» para que la vea. Revisar con **Revisar la entrega**.
- **Pasante:** Pasantías > Mis tareas. Marcar los puntos cumplidos, subir archivos, completar
  el **Informe de avance** y **Entregar**. Trabajo del equipo muestra lo que entregaron los
  compañeros.

## Primer ingreso

Las contraseñas no se migraron. Cada persona recibe un correo para definir la suya o la define
desde «¿Olvidó su contraseña?» en la pantalla de ingreso.
