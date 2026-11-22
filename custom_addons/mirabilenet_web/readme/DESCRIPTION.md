Las páginas de MIRABILENET dentro del módulo **Sitio web** de Odoo Community. Fase 7, parte A.

## Cómo está hecho

Por decisión del 20/11/2026 el sitio usa el módulo `website` de Odoo, no las plantillas del
sistema anterior. Así comparte cabecera, menú, pie y editor con el resto de aplicaciones de
sitio web (tienda en línea, blog, eventos) y se integra con ellas al instalarlas. El estilo
es el de Odoo.

| Parte | Dónde |
|---|---|
| Páginas (QWeb sobre `website.layout`) | `views/templates.xml` |
| Rutas | `controllers/main.py` |
| Menú del sitio | `data/website_menu_data.xml` |
| Contenidos | `models/mirabilenet_web_*.py` |
| Consultas (sobre `crm.lead`) | `models/crm_lead.py` |
| Textos de partida | `web/contenido_inicial.py`, `models/mirabilenet_web_settings.py` |

Direcciones: `/`, `/servicios`, `/servicios/<id>`, `/planes`, `/cobertura`, `/proyectos`,
`/proyectos/<id>`, `/preguntas-frecuentes`, `/contacto`, `/gracias`, `/privacidad`,
`/cookies` y `/terminos`. Las mismas con barra final también responden. `robots.txt` y
`sitemap.xml` son los de Odoo, y el mapa incluye estas páginas.

La portada es de este módulo (reemplaza la página de inicio de Odoo). Todas las páginas se
pueden retocar con el editor del sitio: admiten bloques arriba y abajo.

## Reglas que cumple

- **Planes:** solo salen los activos, marcados «Publicar en la web» y con precio mayor a cero.
- **Textos legales** con versión y fecha de vigencia. Sin documento cargado la página
  responde 404. No admiten HTML: `#` es subtítulo y `-` es viñeta.
- **Lo que escribió el visitante no se edita.** Para anotar algo está la nota interna.
- **Convertir una consulta en prospecto es manual**, con el botón de la consulta.
- **Publican gerencia y administración regional.** Las localidades con cobertura, además,
  solo las de su región.
- Formulario protegido: campo trampa, tiempo mínimo de 3 segundos, vencimiento a las 6 horas
  y tope de 5 consultas por hora desde una misma conexión.

## Lo que cambió respecto al sitio anterior

- **Ya no rige «sin recursos de terceros».** El sitio carga los estilos, tipografías y
  programas de Odoo. Las cookies declaradas son `session_id` y `frontend_lang`; si se activa
  analítica, mapas o la barra de cookies de Odoo, hay que declararlas en `SITE_COOKIES`.
- El diseño propio (hoja de estilos, tipografías, logotipo animado) no se conservó.
- No se emiten los datos estructurados de la portada; Odoo tiene sus propias opciones de
  posicionamiento por página.

## Páginas editables y bloques dinámicos (22/11/2026)

La portada y las páginas de Servicios, Planes, Cobertura, Proyectos y Preguntas frecuentes son
páginas normales del sitio de Odoo: todo se edita, se mueve y se estiliza desde el editor
(Sitio web > Editar), como cualquier página creada en Odoo.

- **Partes fijas** (titular, textos, botones, «Hablemos»): bloques de Odoo. Se escriben en el
  editor; ya no salen de la Configuración del sitio (los campos del titular quedan sin uso en
  estas páginas).
- **Listas** (servicios, planes, cobertura, proyectos, preguntas, ventajas, cifras y aliados):
  **bloques dinámicos** de Odoo. Los datos siguen saliendo de MIRABILENET > Sitio web y solo
  sale lo publicado; el bloque se mueve, se estiliza y se puede agregar en cualquier página
  desde el grupo **MIRABILENET** del panel de bloques.
- Cada bloque guarda qué lista muestra («data-mn-filter»); el navegador busca su filtro con
  `/mirabilenet/web/filtro`. Los filtros leen con privilegios mediante acciones de servidor
  (`website.snippet.filter._mirabilenet_records`) y no aceptan condiciones del navegador.
- Un bloque sin datos publicados no se muestra en el sitio; en el editor se ve con datos de
  muestra. Cada bloque muestra como máximo 16 elementos (límite de Odoo).
- Siguen hechas en código: el detalle de un servicio o proyecto, Contacto (el formulario),
  Gracias y los textos legales, con sus zonas para agregar bloques.
