Asistente para cargar la cartera de una región desde una planilla CSV: planes, clientes,
servicios activos, cuentas PPPoE y ONU. Es la misma importación que se hizo con la planilla de
Yapacaní el 22/11/2026, ahora desde Odoo.

- **Primero revisa, después guarda.** Al subir la planilla muestra un resumen (servicios,
  clientes nuevos y existentes, planes que se crearán, ONU, avisos) sin guardar nada.
- **Planes que no existen:** se crea uno por perfil de Winbox, con el perfil exacto en «Perfil
  PPP», la velocidad que trae el nombre (bajada = subida), el precio de la planilla y TV si el
  perfil dice CATV. Código `<código de región>-<perfil>`. Si ya existe, se usa.
- **Clientes:** uno por persona (mismo C.I. y mismo nombre); residencial y activo.
- **Servicios:** activos, con su modalidad (prepago o pospago), precio y fecha de alta, **sin
  órdenes a los routers** y **sin contrato de cobro**.
- **ONU:** un producto por marca y modelo, y cada serie instalada en el cliente con su MAC.
- **Caja NAP y puerto** (columnas CAJA NAP y PUERTO): conectan cada servicio a su puerto, con
  lo que el puerto muestra la IP del cliente. También para servicios ya importados.
- **Correcciones:** notas dentro del nombre, barrios, C.I. y expedido, MAC con «O» en lugar de
  cero, modelos mal escritos, fechas y coordenadas con coma. Lo que no se puede deducir no se
  inventa: va a la lista «revisar en campo» y a las notas del cliente y del servicio.
- **Otra planilla otro día:** el cliente se reconoce por su usuario PPPoE (o por nombre y C.I.
  si el servicio es nuevo), sin duplicarlo. Lo vacío se completa; lo distinto se lista sin
  cambiarlo, salvo con «Reemplazar con los datos de esta planilla». El plan y la modalidad de
  pago nunca se cambian solos. Un usuario PPPoE de otra región es un error.
- **Repetidos en la planilla:** el usuario PPPoE repetido solo vale la primera vez; la IP
  repetida, o que en Odoo ya es de otro cliente, no se carga dos veces.
- La lectura y la limpieza están en `cartera/limpieza.py`, Python puro sin Odoo.
