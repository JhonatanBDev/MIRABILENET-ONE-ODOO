Red de fibra óptica de MIRABILENET: cajas NAP, sus puertos, los tramos de fibra y los
clientes, con un mapa interactivo (Leaflet de OCA `web_leaflet_lib`, sin CDN).

## Modelos

- **NAP** (`mirabilenet.fiber.nap`): código único (YAP-D-01), nombre NAP (5H, 16I, B1; puede
  repetirse), localidad, zona o barrio, ramal, latitud y longitud (7 decimales), dirección,
  puertos totales (de 8 a 16; una caja nueva nace con el estándar de los ajustes, 8), OLT, puerto PON, color del hilo
  alimentador, estado (activa / por verificar / inactiva / dañada), cifras del relevamiento
  (ocupados y dañados «según el relevamiento», sin clientes), marca «revisar en campo» y su
  nota. Ocupados, libres, dañados y % de ocupación se calculan de los puertos.
- **Puerto** (`mirabilenet.fiber.port`): NAP, número, estado (libre / ocupado / dañado /
  reservado), **servicio** (no cliente: el cliente sale del servicio), fecha de asignación.
- **Tramo** (`mirabilenet.fiber.segment`): código (TR-01), nombre, ramal (lo que va antes de
  «:» en el nombre), tipo (troncal / alimentador / distribución), longitud, vértices, inicio y
  fin, hilos, tipo de cable, estado, color, geometría (JSON con todos los [lat, lon]) y las NAP
  en ruta, **en orden** (`mirabilenet.fiber.segment.stop`).
- Extensiones: el **servicio** (`mirabilenet.service`) gana NAP y puerto; el **cliente** muestra
  su NAP/puerto a través de sus servicios y usa `partner_latitude`/`partner_longitude`
  (`base_geolocalize`) para su punto en el mapa; el **pedido de mantenimiento** de Odoo
  (`maintenance.request`) gana servicio, NAP y puerto para registrar averías.

## Reglas

- Al definir o cambiar los puertos totales se crean o quitan puertos. Nunca se quita un puerto
  con servicio: se avisa con un error claro.
- Un puerto ocupado siempre tiene servicio y uno libre nunca. Asignar un servicio lo ocupa;
  quitarlo lo libera (un puerto dañado sigue dañado). Un servicio tiene un solo puerto.
- Un servicio dado de baja libera su puerto.
- El usuario de fibra puede asignar, liberar o marcar el estado de un puerto, pero no cambiar
  su NAP ni su número. Solo el gestor crea y modifica NAP y tramos, importa y mueve marcadores
  (se comprueba también en el servidor).
- Aislamiento por región (NAP y tramos con región obligatoria; puertos y paradas la toman de
  su NAP o tramo) y regla multicompañía.
- Los textos están escritos en español directamente, como en el resto de los módulos propios:
  no hay carpeta `i18n`.
