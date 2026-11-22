- **Grupos.** «MIRABILENET / Fibra: usuario» (lee la red de su región y asigna o libera
  puertos) y «MIRABILENET / Fibra: gestor» (todo, importaciones y mover marcadores). Los dan los
  roles: superadministrador y administrador regional → gestor; NOC y técnico → usuario.
- **Umbral de baja ocupación.** Ajustes → Red de fibra (o MIRABILENET → Red de fibra →
  Configuración → Ajustes). Se guarda en el parámetro `mirabilenet_fibra.low_occupancy_threshold`;
  vale 30 % si no se define.
- **Mapa.** Depende de `web_leaflet_lib` (OCA geospatial, ya en el `addons_path`). Las teselas
  son remotas: Esri World Imagery (predeterminada) y OpenStreetMap. Sin internet el mapa sigue
  mostrando marcadores y líneas sobre fondo gris.
- **Instalar / actualizar:**
  `python odoo-bin -c odoo.conf -d <base> -i mirabilenet_fibra` (o `-u mirabilenet_fibra`).

- **Puertos por caja NAP** (Ajustes > Red de fibra, por defecto 8): con cuántos puertos nace
  cada caja nueva. «Aplicar a las cajas sin puertos» lleva al estándar las que todavía no los
  tienen; una caja ya definida (por ejemplo, de 16) no se toca.
