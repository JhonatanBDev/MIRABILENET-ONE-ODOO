# Estándar de los módulos propios (Odoo 19 / OCA)

Todo módulo de `custom_addons/` sigue esta estructura. Se toma de las guías de OCA
(https://github.com/OCA/odoo-community.org/blob/master/website/Contribution/CONTRIBUTING.rst).

```
mi_modulo/
├── __init__.py
├── __manifest__.py
├── controllers/          main.py y uno por área
├── data/                 XML y CSV de datos (nada de Python)
├── demo/
├── models/               un archivo por modelo, con el nombre del modelo
├── report/               plantillas e ir.actions.report
├── security/             ir.model.access.csv y <modulo>_security.xml (grupos y reglas)
├── static/description/   icon.png
├── tests/                test_*.py
├── views/                <modelo>_views.xml y <modulo>_menus.xml
├── wizards/              un archivo por asistente y su <asistente>_views.xml
├── <paquete>/            Python puro sin Odoo (siat/, isp/, whatsapp/, migracion/, ...)
└── readme/               DESCRIPTION.md, CONFIGURE.md, USAGE.md, ROADMAP.md
```

## Reglas

- **Un modelo, un archivo**, con el nombre técnico: `crm.lead` → `models/crm_lead.py`;
  `mirabilenet.web.service` → `models/mirabilenet_web_service.py`. Las extensiones de
  modelos de Odoo van en el archivo del modelo que extienden.
- **Vistas:** `views/<modelo>_views.xml` (lista, formulario, búsqueda y acción del modelo);
  los menús juntos en `views/<modulo>_menus.xml`, cargados después de las vistas.
- **Orden de `data` en el manifiesto:** seguridad (grupos, reglas, accesos), datos, vistas,
  menús, informes, asistentes. Dos excepciones, con un comentario en el manifiesto:
  - si un menú abre la acción de un asistente, las vistas del asistente van antes de los menús;
  - si un dato usa un informe (por ejemplo, una plantilla de correo que lo adjunta), el
    informe va antes de ese dato.
- **Manifiesto:**
  - `name`, `summary`, `version` `19.0.x.y.z`, `category`, `author` `"MIRABILENET"`.
  - `license` `"AGPL-3"` en todos (varios dependen de módulos AGPL de OCA).
  - `depends`, `data`, `installable`, `application`.
  - Una `description` corta, para que Odoo no intente leer otro archivo como RST.
- **Documentación** en `readme/`: DESCRIPTION (qué hace y reglas), CONFIGURE, USAGE, ROADMAP
  (pendientes). No hay `README.md` en la raíz del módulo.
- **Datos en Python** (textos de partida, contenido inicial) no van en `data/`: van en el
  paquete de Python puro del módulo o en `models/`.
- **Python puro** (lógica sin Odoo: protocolos, cálculos, clientes de API) en un paquete con
  nombre propio dentro del módulo; no importa nada de `odoo`.
- **Nombres:** clases `CamelCase` con el nombre del modelo; métodos privados con `_`; acciones
  públicas `action_*`; campos propios en modelos de Odoo con prefijo `mirabilenet_` (o
  `mira_siat_` en el SIAT).
- **Pruebas:** `tests/test_<area>.py`, etiquetadas `mirabilenet` (o `mira_siat`),
  `post_install`, `-at_install`.
