Los cobros con lo que Odoo ya trae. Sustituye a `mirabilenet_cobros` (modelo propio de avisos,
pagos, recibos y caja) por una adaptación pequeña sobre:

| Necesidad | Quién lo hace |
|---|---|
| Emisión mensual, prepago y pospago | `contract` (OCA, 19.0) |
| Aviso de cobro, saldo, vencimiento | Factura de Odoo (`account.move`) |
| Pagos, pagos parciales, recibo | Pagos de Odoo (`account.payment`) |
| Factura fiscal | `mira_sale_siat`, con su botón en la misma factura |

## Lo único que añade este módulo

- **Servicio → contrato.** Al activarse un servicio por primera vez se crea su contrato, con el
  plan y el precio mensual del servicio. Si cambia el precio del servicio, el contrato lo sigue.
- **Prepago: todos el mismo día.** Cobra por mes calendario y la factura, que es el aviso
  de cobro, sale para todos el «día de emisión (prepago)» de la región, por ejemplo el 1 de
  cada mes. El primer mes se cobra solo por los días desde el alta (módulo OCA
  `contract_variable_qty_prorated`). Vence el «día de vencimiento (prepago)» de la región.
- **Pospago: el día del alta.** Cobra meses enteros contados desde el alta: un alta el 3 de
  noviembre se cobra el 3 de diciembre, el 3 de enero y así. Vence ese mismo día. Las altas
  del 29 al 31 pasan al 28 cuando llega un mes que no tiene ese día, sin perder ni repetir
  días. El servicio muestra su «día de cobro».
- **La factura se publica al emitirse** y lleva su región y su servicio.
- **Corte automático.** A la hora de corte de cada región se pide suspender los servicios
  activos con facturas vencidas hace más días que los días de gracia.
- **Reactivación.** Cuando un pago deja al cliente sin facturas pendientes, se pide reactivar
  sus servicios (si la región lo tiene habilitado). Un pago parcial no reactiva.
- **Baja.** El contrato deja de emitir desde la fecha de baja; si aún no había empezado a
  cobrarse, se archiva.
- **Región.** Facturas, pagos y contratos se ven solo en la región del usuario (los roles
  globales ven todo). Lo que no tiene región, como los asientos contables generales, no se
  filtra.
- **Permisos.** Gerencia, administración regional, finanzas, cajero y cobrador usan el grupo
  de facturación de Odoo; no hay grupos propios.

## Lo que cambia respecto a `mirabilenet_cobros`

- **Ya no hay aprobación de pagos.** Antes el pago de un cajero quedaba pendiente hasta que
  finanzas lo aprobaba. En Odoo el pago se registra y el control es el cierre de caja y la
  conciliación bancaria.
- **Días de cobro:** el prepago sale el día de emisión prepago de la región; el pospago, el
  día del alta de cada servicio. El «día de emisión (pospago)» de la región ya no se usa.
- **Numeración.** Facturas y recibos usan las secuencias de Odoo, no la numeración propia
  por caja.
- **Gastos, caja y arqueo** pasan a Contabilidad y a Punto de venta (paso 2).
- Los apuntes contables (líneas de asiento) no se filtran por región, solo facturas y pagos.

## Lo que usa el resto de MIRABILENET

- `mirabilenet_whatsapp` lee facturas y pagos de Odoo: los recordatorios, la API de n8n (mismas
  rutas y mismos campos) y los comprobantes. Verificar un comprobante registra el pago de Odoo a
  nombre de quien verifica.
- `mirabilenet_contratos_siat` emite la factura fiscal cuando la factura queda pagada, si la
  empresa tiene activado «Emitir la factura fiscal al registrar el pago». Anota quién registró
  el pago. Si el SIN falla, el pago se mantiene y la emisión se reintenta cada 30 minutos.

## Estado

Sustituyó a `mirabilenet_cobros` y `mirabilenet_cobros_siat`, que quedaron apartados en
`retirados/` (fuera de la ruta de módulos) por si hiciera falta consultarlos.
