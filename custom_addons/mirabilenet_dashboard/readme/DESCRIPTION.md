Una sola pantalla con todo el sistema. Es la pantalla de inicio de los usuarios de MIRABILENET.

Secciones (el orden depende del rol, y cada usuario puede ocultar las que no usa):

- **Alertas:** solo aparecen cuando hay algo:
  - routers degradados o desconectados;
  - comprobantes de pago por revisar;
  - facturas vencidas hace más de 30 días;
  - cajas NAP con 2 o más averías;
  - ingreso mensual por debajo del objetivo.
- **Resumen:** clientes activos, ingresos del periodo y altas del periodo (los dos con ▲▼ contra el
  periodo anterior), y cartera vencida.
- **Negocio:**
  - ingreso mensual (MRR) con su avance hacia el objetivo de la región;
  - ARPU, churn del mes y recaudación;
  - gráfico de altas, bajas y altas netas de 6 meses;
  - antigüedad de la cartera (0–30, 31–60, 61–90 y más de 90 días);
  - zonas con más deuda y cajas NAP con más averías.
- **Ingresos vs gastos y estado de servicios.**
- **Actividad, accesos rápidos y puesta en marcha.**
- **Cobranza diaria y por método.**
- **Clientes, cobros y red.**
- **Cartera vencida por cliente y últimos pagos.**
- **Capacidad y soporte.**

Filtros dinámicos:

- **Periodo:** Hoy, 7, 30 o 90 días, Este mes, Mes pasado o fechas a elección.
- **Barra de filtros:** región (usuarios globales), zona, nodo, plan, prepago o pospago, y estado
  del servicio. Se combinan entre sí.
- **Chips:** cada filtro activo se ve como una etiqueta con ✕, más el botón «Limpiar».
- **Desde los gráficos:** clic en un estado de la dona filtra todo el tablero; clic en un mes
  (ingresos, o altas y bajas) pasa el tablero a ese mes. Ctrl+clic abre la lista.
- **Se recuerdan por usuario** (`res.users.settings`), junto con las secciones ocultas.

Cómo funciona:

- Se lee con los permisos del usuario: cada uno ve solo su región. Un filtro de otra región que
  llegue desde el navegador se ignora.
- Cada número abre la lista de lo que cuenta, con los mismos filtros
  (`mirabilenet.dashboard.action_open`).
- Lo que no tiene datos sale como «—» con su aviso, nunca como 0:
  - sesiones PPPoE en línea y tráfico;
  - cuentas desincronizadas mientras no haya un router conectado;
  - gastos, si no hay facturas de proveedor;
  - ocupación, sin capacidad declarada;
  - objetivo de ingreso, sin objetivo o con filtros de plan o nodo.
- Los filtros de zona, nodo, plan y modalidad se aplican a través del servicio. Los pagos,
  comprobantes y casos se filtran por los servicios de su cliente.
- No hay filtro por sucursal: los servicios no tienen sucursal; solo la tienen las cajas.
- Se actualiza solo cada minuto mientras la pestaña está visible. Sigue el modo oscuro.
