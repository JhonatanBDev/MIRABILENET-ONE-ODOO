## Pendientes

- **Datos a levantar en campo:** cantidad de puertos de cada NAP (hoy ninguna la tiene), OLT,
  puerto PON donde falta, color del hilo alimentador, zona o barrio, dirección o referencia,
  ocupación real (qué servicio va en qué puerto), hilos y tipo de cable de los tramos, la
  geometría real de cada tramo (KML de Google Earth) y verificar lo marcado «revisar en campo»
  (YAP-B-04, longitudes de TR-24 y TR-26).
- **Traducciones:** como el resto de los módulos propios, los textos están en español en el
  código y no hay carpeta `i18n` ni `es.po`.
- No se cargan datos iniciales desde `data/`: los CSV se importan con el asistente.
- La zona válida de coordenadas es la de Yapacaní por defecto; para otra región se cambia en
  el asistente.
- El mapa carga toda la red de la región de una vez; con miles de clientes convendría
  agrupar marcadores (`leaflet.markercluster` ya viene en `web_leaflet_lib`).
- Las teselas son remotas (Esri, OSM); no hay caché local.
- Las pantallas se probaron con pruebas automáticas y una carga del servidor; conviene una
  revisión en el navegador.
