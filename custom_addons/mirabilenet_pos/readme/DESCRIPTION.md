Cada sucursal atiende con el **Punto de venta** de Odoo. Este módulo solo une el punto de venta
con la sucursal y la venta con la red. OCA no tiene para la 19 nada que cubra esto.

## Lo que añade

- **Sucursal en el punto de venta.** Campo «Sucursal» en la configuración del punto de venta
  (MIRABILENET > Organización > Cajas de sucursal). Con eso el punto de venta, sus sesiones y
  sus ventas quedan en la región de la sucursal y solo los ve el personal de esa región (los
  roles globales y el administrador técnico ven todo).
- **Lista de precios de sucursal.** Al asignar la sucursal, el punto de venta usa como única
  lista «Sucursales MIRABILENET» (se apaga «varias listas de precios»), que deja los planes en 0: en caja no se cobra la mensualidad, la
  factura el contrato del servicio desde el día del alta (ver `mirabilenet_contratos`).
- **Producto «Instalación del servicio»**, a precio 0: el cajero escribe el monto cotizado.
- **Vender un plan es solicitar el servicio.** Al pagarse la venta, por cada plan se crea un
  servicio «Pendiente de instalación» a nombre del cliente, en la región de la sucursal y con
  la dirección del cliente. El cliente queda marcado como cliente de MIRABILENET, con región y
  sucursal si no las tenía, en estado «Instalación pendiente». Queda en la auditoría.
- **Sin cliente no hay solicitud:** una venta con un plan y sin cliente elegido se rechaza.
- Los planes nuevos se ofrecen solos en el punto de venta y van a la categoría «Planes de
  internet».
- Permisos con los grupos de Punto de venta: gerencia y administración regional lo
  administran; cajero, cobrador y vendedor lo usan.

## Lo que no hace, y dónde está

- **Cobrar la mensualidad en caja.** El cobro de facturas pendientes desde el Punto de venta
  es de Odoo Enterprise. En Community el cajero registra el pago desde la factura
  (MIRABILENET > Cobros > Facturas a clientes > Registrar pago), con el diario de caja de su
  sucursal.
- Una sucursal en otra moneda o empresa necesita su propia lista de precios.
- **Lista de precios de las sucursales** («Sucursales MIRABILENET», planes a Bs 0 en caja):
  funciona con la opción «Listas de precios» de Ajustes apagada, a propósito (encendida, las
  ventas y el sitio tomarían esa lista). Guardar Ajustes no la archiva y el aviso «se
  archivarán todas las listas de precios activas» no sale por ella.
