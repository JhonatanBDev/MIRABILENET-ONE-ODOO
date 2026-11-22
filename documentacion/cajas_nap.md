Estamos desarrollando en Odoo 19 Community. Necesito crear un NUEVO MÓDULO para gestionar la red de fibra óptica (cajas NAP, puertos, tramos y clientes) con un mapa interactivo.

## PASO 0 – Antes de escribir código
Revisa los módulos propios que ya creamos en este proyecto (carpeta addons custom) y replica EXACTAMENTE su estructura y convenciones:
- prefijo/nombre técnico de módulos, estructura de carpetas, __manifest__.py (autor, categoría, versión, license, depends)
- convención de nombres de modelos, campos, vistas, menús, grupos de seguridad, ir.model.access.csv, reglas, secuencias
- estilo de vistas XML, uso de data/ vs demo/, traducciones (i18n es), idioma de etiquetas (español)
Dime qué convenciones detectaste antes de generar archivos. Nombre sugerido del módulo: <prefijo_existente>_fibra_nap (ajústalo a nuestra convención). Debe ser un módulo independiente que dependa de base, mail, contacts (y base_geolocalize si aplica) y, opcionalmente, del módulo de suscripciones/facturación que ya tengamos, solo si ya existe.

## Contexto de negocio
Una caja NAP tiene entre 8 y 16 puertos. Cada puerto se asigna a un cliente. Objetivos:
1. Registrar las NAP en un mapa y registrar a qué puerto está conectado cada cliente.
2. Reparaciones más rápidas: ubicar la NAP y el puerto exacto del cliente con falla.
3. Saber si un puerto está disponible o no, para verificarlo al instalar a un cliente nuevo.
4. Evaluar en qué zonas hay pocos clientes (baja ocupación) para enfocar la promoción.
5. Que los clientes aparezcan en el mismo mapa.

## Modelos (Odoo 19)
1. `fibra.nap`: codigo (único, ej. YAP-D-01), nombre_nap (NO único: hay repetidos como "K", "6K", "1H"), localidad, zona_barrio, ramal, latitud, longitud (Float con digits (10,7)), direccion_referencia, puertos_totales (entero entre 8 y 16, o selection 8/12/16), olt, puerto_pon, color_de_hilo_alimentador, estado (activa / por_verificar / inactiva / danada), company_id, active, notas. Campos computados almacenados: puertos_ocupados, puertos_libres, puertos_danados, porcentaje_ocupacion. Chatter (mail.thread).
2. `fibra.nap.puerto`: nap_id, numero (1..N), estado (libre / ocupado / danado / reservado), partner_id (cliente), fecha_asignacion, notas. Restricciones SQL: (nap_id, numero) único; un cliente no puede tener dos puertos activos a la vez (si hay que permitirlo, avísame). Al definir o cambiar puertos_totales en la NAP, generar/ajustar automáticamente los puertos (nunca borrar un puerto ocupado).
3. `fibra.tramo`: codigo (TR-01...), nombre, tipo (troncal / alimentador / distribucion), longitud_m, vertices, lat_inicio, lon_inicio, lat_fin, lon_fin, hilos, tipo_cable, estado (activa / por_verificar), nap_ids (Many2many a fibra.nap; guardar el orden de la ruta en una tabla intermedia si es viable), y además:
   - `color` (Char hex, widget de color). Si está vacío, usar un color por defecto según tipo; editable por tramo. En nuestra referencia en Google Earth: ruta H en verde, ruta I y línea B en rojo, ramal 15I-16I en azul.
   - `geometria_json` (Text): lista ordenada de [lat, lon] con TODOS los vértices del recorrido real por las calles (el CSV trae `vertices` con la cantidad de puntos; ej. TR-02 tiene 68).
4. Extender `res.partner` (herencia) con: nap_id, puerto_id (Many2one a puerto libre de esa NAP), latitud/longitud del cliente (reutilizar partner_latitude/partner_longitude si base_geolocalize está disponible, sin duplicar). Al asignar puerto en el cliente, el puerto pasa a "ocupado" y viceversa (lógica bidireccional coherente, con onchange/domain para ofrecer solo puertos libres).
5. Opcional pero deseable: wizard "Asignar cliente a puerto" y smart buttons (en la NAP: "Clientes"; en el cliente: "NAP/Puerto").

## Mapa (punto crítico) – debe verse como nuestra referencia de Google Earth
Odoo 19 Community NO incluye la vista map (es Enterprise); NO uses web_map. Impleméntalo como client action / vista con OWL + Leaflet (librería empaquetada localmente en static/lib, sin CDN para el JS/CSS).

Referencia visual: imagen satelital de fondo, marcadores cuadrados con borde blanco, etiquetas de código grandes y siempre visibles, y líneas gruesas de colores que siguen las calles.

### Capas base
- Selector de capa base: Satélite (Esri World Imagery) como predeterminada y OpenStreetMap como alternativa. Si no hay internet, el mapa debe seguir funcionando mostrando solo marcadores y líneas.

### Marcadores de NAP
- Icono tipo L.divIcon cuadrado (~18-22 px), borde blanco de 3 px y relleno según estado/ocupación: verde = libres suficientes, amarillo = casi llena, rojo = llena, negro = dañada, gris/negro tenue = por_verificar o sin datos de puertos.
- Etiqueta PERMANENTE junto al marcador con `nombre_nap` (ej. 5H, 16I, B1): texto blanco, negrita, grande (~14-16 px), con contorno/halo oscuro (text-shadow o -webkit-text-stroke) para que resalte sobre la imagen satelital, legible sobre fondo claro y oscuro.
- Las etiquetas se muestran desde un zoom mínimo (≈16) y se ocultan por debajo para no saturar; con anti-solapamiento básico si es posible.
- Ojo: `nombre_nap` se repite en el CSV (K/K, 6K/6K, 1H en las series H y H2). La etiqueta muestra `nombre_nap`; el popup y el tooltip muestran siempre el `codigo` único (YAP-H-01 vs YAP-H2-01) y el ramal.
- Popup: código, nombre, ramal, estado, puertos libres/totales y botón "Abrir NAP".

### Marcadores de clientes
- Icono distinto al de las NAP, en su ubicación, enlazados a su NAP/puerto. Popup con nombre, teléfono, NAP y puerto.

### Tramos (líneas)
- Polilíneas gruesas (weight 4-5, opacity ~0.9) con el `color` propio del tramo, dibujadas con `geometria_json`.
- Si `geometria_json` está vacío, dibujar línea recta inicio→fin con trazo discontinuo, para que se note que falta el recorrido real.
- Popup del tramo: código, nombre, longitud_m, estado y NAP en ruta (en orden).
- Las líneas van debajo de los marcadores (z-order) para que los cuadrados queden encima.

### Interacción
- Filtros por ramal, estado, tipo de tramo y "solo NAP con puertos libres"; capa de clientes on/off; buscador por código de NAP o nombre de cliente.
- Fit bounds inicial sobre los datos (Yapacaní ronda lat -17.40, lon -63.88).
- Menú "Mapa de fibra" y apertura del mapa centrado en una NAP desde su formulario.
- Arrastrar un marcador de NAP para corregir latitud/longitud y guardar (solo grupo gestor).
- Leyenda fija en una esquina con el significado de los colores de marcadores y de líneas.

## Reportes/análisis de cobertura
- Vista lista y pivot/graph de NAP: ocupación por ramal y por zona_barrio.
- Filtro/agrupación "Zonas con pocos clientes" (ocupación < umbral configurable en ajustes, ej. 30 %) para decidir dónde promocionar.
- Vista de lista de puertos libres por NAP, útil para el instalador.

## Importación de datos (adjunto 2 CSV)
Archivos: naps_yapacani.csv (112 NAP) y tramos_fibra_mapa.csv (27 tramos). Formato: separador ";", UTF-8 con BOM, saltos CRLF; hay una fila vacía al final de tramos (ignorarla).

Problema grave en coordenadas: vienen con puntos como separador de miles. Ejemplos: "-17.404.864" debe ser -17.404864 y "-63.884.567" → -63.884567; en tramos, "-174.055.798.604.324" → -17.4055798604324 y "-6.388.524.129.690.300" → -63.885241296903. Regla: quitar todos los puntos, conservar el signo y colocar el punto decimal después de los 2 primeros dígitos. Algunas filas de tramos traen distinta cantidad de dígitos (p. ej. "-1.741.648.787.684.930"): aplica la misma regla y valida que el resultado quede dentro de lat [-17.5, -17.3] y lon [-64.0, -63.8]. Las filas que no cumplan se importan con coordenada vacía y se reportan en un log, NO se descartan en silencio.

Reglas de importación:
- Idempotente: upsert por `codigo`.
- Columna `naps_en_ruta` de tramos: texto tipo "B1 (YAP-B-01), 1D (YAP-D-01)"; extraer los códigos entre paréntesis y vincular a fibra.nap; reportar los que no existan.
- Los datos operativos vacíos (puertos_totales, olt, direccion, etc.) quedan vacíos; no inventes valores. Si puertos_totales está vacío, la NAP queda sin puertos generados y con una advertencia visible "Falta definir cantidad de puertos".
- Estados: respetar "activa" / "por_verificar" tal como vienen (la mayoría está por_verificar, es normal).
- Implementar como wizard de importación en el menú de configuración (subir CSV) y cargar además los datos iniciales desde data/ si es práctico. Al terminar, mostrar resumen: creados, actualizados, con error.

### Importar geometría desde Google Earth (KML/KMZ)
- Wizard "Importar KML/KMZ": leer Placemarks tipo LineString (recorridos) y Point (NAP).
- Los LineString se asocian al tramo por nombre/código (ej. "Ruta I: Central - 1I a 14I" ↔ TR-23), mostrando una tabla de coincidencias para confirmar manualmente las dudosas. El color del KML (formato aabbggrr) se convierte a hex y se guarda en `color`.
- Los Point se asocian a NAP por nombre y actualizan latitud/longitud previa confirmación.
- Recalcular `longitud_m` (haversine) y `vertices` desde la geometría y avisar si difieren más de un 10 % de lo cargado desde el CSV.
- Las coordenadas del KML vienen como lon,lat,alt; invertir al orden [lat, lon] para Leaflet.

## Seguridad
Grupos: Usuario fibra (lectura + asignar puertos) y Gestor fibra (CRUD completo, importar, mover marcadores). ir.model.access.csv y reglas multi-compañía según nuestra convención.

## Requisitos técnicos Odoo 19
- Vistas con `<list>` (no `<tree>`), view_mode "list,form", sin `attrs`/`states` (usar `invisible=`, `readonly=`, `required=` con expresiones), `<chatter/>` en formularios.
- Assets del mapa declarados en `web.assets_backend` en el manifest; componentes OWL modernos.
- Código y comentarios claros; textos de UI en español; archivos i18n/es.po.
- Pruebas básicas (TransactionCase) para: generación de puertos, asignación/liberación de cliente, parser de coordenadas, parser de naps_en_ruta y parser de KML.

## Entregables
1. Resumen de convenciones detectadas en nuestros módulos y plan del módulo.
2. Árbol de archivos completo y el código de cada archivo.
3. Instrucciones para instalar/actualizar (`-i` / `-u`) y probar con los 2 CSV.
4. Lista de supuestos y de datos faltantes que debo levantar en campo (puertos por NAP, OLT, ocupación real, geometría de los tramos).