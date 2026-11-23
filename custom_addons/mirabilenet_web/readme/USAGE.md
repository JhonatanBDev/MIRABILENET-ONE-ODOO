## Dónde se administra

MIRABILENET > Sitio web: Consultas, Configuración del sitio, Servicios, Cobertura, Proyectos,
Preguntas frecuentes, Ventajas, Cifras, Tecnologías y aliados, Textos legales.

El aspecto, el menú, el logotipo y el pie se editan desde la aplicación **Sitio web** de Odoo.
El botón «Cargar contenido inicial» (Configuración del sitio) trae los textos de partida del
sistema anterior sin pisar lo ya escrito.

## Editar el sitio

Sitio web > **Editar**. Arrastre bloques de Odoo o del grupo **MIRABILENET** (Servicios,
Planes de internet, Cobertura, Proyectos, Preguntas frecuentes, Ventajas, Cifras, Tecnologías y
aliados). Los botones, textos e imágenes se sueltan dentro de cualquier bloque. Los datos de
las listas se cargan en MIRABILENET > Sitio web; «Cargar contenido inicial» trae los textos de
partida. Para que el plan salga en el sitio: «Publicar en el sitio» y precio mayor que cero.

## Estilo del sitio

El sitio tiene un estilo limpio, de titulares grandes, mosaicos redondeados y tarjetas de
producto (`static/src/scss/sitio.scss`). El estilo solo da forma a unas clases; el contenido se
sigue cambiando con **Editar**:

- **Portadas** (clase `mn_hero`): título, texto, botón, enlace con flecha (`mn_link`) e imagen
  (`mn_art`). Para una portada oscura, elija un fondo oscuro en el editor.
- **Mosaicos** (`mn_tiles` y, dentro, `mn_tile`): dos por fila. Se duplican, se mueven y se
  borran como cualquier columna. `mn_tile_dark` lo pone oscuro.
- **Tarjetas de planes** (`mn_plan`): salen solas en el bloque «Planes de internet» por cada
  plan publicado con precio. La segunda lleva la marca «Más contratado». Si en Configuración
  del sitio se ocultan los precios, dicen «A cotizar».
- **Imágenes:** las ilustraciones son propias (`static/img/`, generadas con
  `documentacion/herramientas/generar_ilustraciones_sitio.py`). Para poner una foto, clic en la
  imagen > Reemplazar.

Si una página ya se había editado a mano, Odoo guarda esa copia y la muestra en lugar de la
plantilla nueva. Para volver a la del módulo: Sitio web > Sitio > Editor HTML/CSS, elegir la
página y «Restablecer».
