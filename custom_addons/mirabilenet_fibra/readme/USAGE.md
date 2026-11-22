## Importar el relevamiento

MIRABILENET → Red de fibra → Configuración → **Importar CSV de NAP y tramos**. Elija la región
y suba los dos CSV juntos (`naps_yapacani.csv` y `tramos_fibra_mapa.csv`): varias correcciones
cruzan las NAP con los tramos. Si sube uno solo, el otro lado se toma de lo ya cargado.

- Separador «;», UTF-8 con o sin BOM, CRLF; las filas vacías se saltan. Los encabezados se
  reconocen sin importar mayúsculas, tildes ni espacios (`Código` = `codigo`). Una columna
  desconocida se informa y se ignora.
- NAP: `codigo, nombre_nap, localidad, zona_barrio, ramal, latitud, longitud,
  direccion_referencia, puertos_totales, puertos_ocupados, puertos_danados, olt, puerto_pon,
  color_de_hilo_alimentador, estado`.
- Tramos: `codigo, nombre, tipo, longitud_m, vertices, naps_en_ruta, lat_inicio, lon_inicio,
  lat_fin, lon_fin, hilos, tipo_cable, estado` y, si vienen, `color` y `geometria_json`.
- Se actualiza por `codigo`: importar dos veces no duplica. Cada dato ya cargado que el
  archivo reemplaza queda en el registro («actualizado: campo «antes» → «después»»). Con
  **«Conservar los datos ya cargados»** el archivo solo completa lo vacío: lo distinto (por
  ejemplo, algo corregido en Odoo) se conserva y se anota. Úselo al completar con un archivo de
  otro día. Un dato vacío no borra lo ya
  cargado ni se inventa. Una NAP nueva sin `puertos_totales` nace con los puertos estándar de
  los ajustes (8).
- Coordenadas con puntos de miles: se quitan los puntos, se conserva el signo y se pone el
  decimal tras los dos primeros dígitos (`-17.404.864` → -17.404864). Si el resultado cae fuera
  de la zona del asistente (Yapacaní: lat -17,5 a -17,3; lon -64,0 a -63,8) se importa vacía, se
  informa y la NAP o el tramo queda «revisar en campo».
- `puertos_ocupados` y `puertos_danados` son cifras sin clientes: se guardan como «según el
  relevamiento». Nunca se ocupa un puerto sin servicio; sí se marcan como dañados tantos puertos
  libres como diga el relevamiento, si la NAP tiene puertos definidos.
- `naps_en_ruta` («B1 (YAP-B-01), 1D (YAP-D-01)»): se toman los códigos entre paréntesis, en
  orden; los que no existen se informan.

### Correcciones deducidas («Aplicar correcciones deducidas», activada por defecto)

Reglas generales de `fibra/deduce.py`; cada cambio aparece en el registro como
«deducido: campo «antes» → «después» (motivo)».

1. **Ramal.** El ramal de un tramo es lo que va antes de «:» en su nombre (o antes de « - » si
   no hay «:»). Una NAP sin ramal toma el del tramo de distribución o alimentador que la
   contiene; la NAP donde arranca un ramal y las de un tramo que deriva de otro quedan en la ruta
   de la que se derivan; si solo está en el troncal, el del troncal; si queda entre dos ramales,
   vacía y con aviso «ambiguo». Las escrituras distintas del mismo ramal (mayúsculas, tildes,
   signos, «de») se unifican.
2. **Tildes.** «Espana» → «España» en los nombres de tramo (tabla ampliable `ACCENT_FIXES`).
3. **Puerto PON.** Una NAP sin puerto PON toma el de su serie (letras del código: A, H2, K…) y
   ramal, si todas las que lo tienen comparten uno solo.
4. **Revisar en campo** (no cambian datos): NAP en ningún tramo o a más de 1 km de la NAP más
   cercana de su serie; tramo cuyo nombre dice un largo («(480M)») que difiere más de un 10 % de
   `longitud_m`; tramo con `longitud_m` menor que el recorrido inicio → NAP → fin; tramo que
   empieza a más de 100 m de su primera NAP (informativo).
5. **Colores de tramo** (si el tramo no trae color; siempre editable después): uno por ramal.

| Ramal / tipo | Color |
|---|---|
| Troncal (tipo) | `#f57c00` naranja (línea más gruesa) |
| Alimentador (tipo) | `#8e24aa` violeta |
| Ruta H oeste | `#2e7d32` verde oscuro |
| Ruta H sur | `#66bb6a` verde medio |
| 6IZ | `#00e676` verde brillante |
| 6IZ_EXT | `#69f0ae` verde menta |
| 6DE | `#9ccc65` verde oliva claro |
| 6DE_EXT | `#aeea00` verde lima |
| Ruta I | `#c62828` rojo oscuro |
| LINEA B | `#ff5252` rojo claro |
| Ruta I ramal (4I-15I-16I) | `#2962ff` azul |
| 3DE | `#00e5ff` cian |
| 3IZ | `#ffd600` amarillo |
| 5DE | `#ff4081` rosa |
| 5DE_EXT | `#00bfa5` verde azulado |
| 5IZ | `#e040fb` magenta |
| 5IZ_EXT | `#ffab00` ámbar |
| 7DE_1 | `#536dfe` índigo |
| 7DE_2_EXT | `#c6ff00` lima |
| Ruta B/ España, San Francisco y Floresta | `#a1887f` marrón claro |
| Ruta B/ Santa Cruz y Villa Santiago | `#4dd0e1` aguamarina |
| Ruta D | `#0091ea` celeste |
| Ruta España, San Francisco y Los Pioneros | `#b388ff` lavanda |
| Ruta J norte | `#fbc02d` dorado |
| Ruta J sur | `#ff9e80` salmón |
| Ruta K sur | `#f48fb1` rosa claro |

Las pistas de Google Earth (familia H en verdes, ruta I y línea B en rojos, 4I-15I-16I en
azul) están en `RAMAL_COLORS`; los demás ramales toman `PALETTE` en orden alfabético.

## Importar recorridos de Google Earth

Configuración → **Importar KML/KMZ**. Los LineString se asocian al tramo por código o nombre y
los Point a la NAP por código o nombre NAP. La tabla muestra cada coincidencia; las dudosas
(nombre parecido o nombre NAP repetido) quedan sin marcar. Al aplicar, el recorrido se guarda
en la geometría, el color KML (aabbggrr) pasa a hex, se recalculan longitud (haversine) y
vértices y se avisa si difieren más de un 10 % de lo cargado.

## Trabajo diario

- **Ubicar cliente (por IP)** (Red de fibra, o el botón «Ubicar» del servicio y «Ubicar cliente»
  de la avería): con la IP, el usuario PPPoE, el nombre o el C.I. muestra la caja NAP y el
  puerto del cliente, la dirección o referencia de la caja, el enlace «Cómo llegar» de Google
  Maps, el ramal, la OLT y el puerto PON, y la tabla de los puertos de esa caja con el cliente,
  la IP y las averías abiertas de cada uno. Con 2 o más averías abiertas en la misma caja avisa
  «revise primero la caja y el tramo que la alimenta»; si no, sugiere revisar el equipo o el
  cable del cliente. Desde ahí se abre el mapa, la caja o se registra la avería.
- Cada **puerto** muestra la IP y el usuario PPPoE del servicio conectado y se puede buscar
  por IP.

- **Mapa de fibra**: filtros por ramal, estado de NAP, tipo de tramo y «solo NAP con puertos
  libres», capa de clientes, buscador por código de NAP o nombre de cliente, leyenda y barra
  de avisos de datos (cada aviso lleva a su NAP o tramo). El gestor arrastra una NAP para
  corregir su ubicación. Desde una NAP, un tramo, un servicio o una avería, «Ver en el mapa».
- **Asignar un puerto**: en el servicio elija la NAP y un puerto libre, o desde el puerto use
  «Asignar cliente». «Puertos libres» lista, por NAP, los disponibles para el instalador.
- **Averías**: pedido de mantenimiento con el servicio; NAP y puerto se completan solos.
- **Cobertura**: ocupación por ramal y zona (pivote y gráfico), «Zonas con pocos clientes»
  (por debajo del umbral) y «Revisar en campo».
