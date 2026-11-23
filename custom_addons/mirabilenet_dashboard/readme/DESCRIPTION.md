Una sola pantalla con todo el sistema, como el dashboard de MIRABILENET ONE. Es la pantalla de
inicio de los usuarios de MIRABILENET.

- **Resumen:** clientes activos, ingresos del periodo, servicios totales y cartera vencida.
- **Ingresos vs gastos** de los últimos 6 meses, **estado de servicios**, **actividad reciente**
  (auditoría), **accesos rápidos** y **puesta en marcha** (8 pasos, con «Configurar →»).
- **Cobranza diaria y por método** (efectivo, QR, transferencia), **clientes** por estado,
  **cobros**, **red** (routers, cuentas PPPoE), **capacidad** (nodos y puertos NAP),
  **soporte** (averías y casos), **cartera vencida** por cliente y **últimos pagos**.

Cómo funciona:

- Se lee con los permisos del usuario: cada uno ve solo su región. Los usuarios globales
  (superadmin, gerencia, auditor) eligen una región o ven todas. Lo que un rol no puede ver sale
  como «—».
- Lo que no tiene datos sale como «—» con su aviso, nunca como 0: sesiones PPPoE en línea y
  tráfico (todavía no se leen del router), gastos (si no hay facturas de proveedor), ocupación
  (si ningún nodo declara capacidad).
- Cada número abre la lista de lo que cuenta, con el mismo filtro
  (`mirabilenet.dashboard.action_open`).
- Se actualiza solo cada minuto mientras la pestaña está visible. Sigue el modo oscuro.
- Los ingresos son los pagos de cliente registrados en Odoo (`account.payment`), igual que el
  informe de cobranza de `mirabilenet_indicadores`.
