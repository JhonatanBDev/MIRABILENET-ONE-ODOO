# Puesta en marcha (fase 10)

Preparado el 20/11/2026, **sin ejecutar nada en el VPS**. Cada paso contra producción se
confirma con el usuario uno por uno.

| Documento | Punto de la guía |
|---|---|
| `01_operacion_en_paralelo.md` | 1. Operación en paralelo, empezando por una región |
| `02_dia_del_cambio.md` | 2 y 3. Comprobaciones del día, vuelta atrás, webhook de WhatsApp y n8n sin editar los flujos |
| `03_respaldos.md` | 4. Respaldos fuera del servidor y su restauración (probada en desarrollo) |
| `04_manual_de_usuario.md` | 5. Manual de las pantallas de Odoo |
| `../../deploy/` | 6. Docker Compose del VPS: Odoo, PostgreSQL, addons propios y de terceros |

## Archivos de `deploy/`

- `docker-compose.yml`: Odoo 19 (imagen oficial) y su PostgreSQL; monta `custom_addons`, `oca`
  y la carpeta de WireGuard del sistema anterior; entra a la red de ese sistema como `odoo`.
- `docker-compose.cambio.yml`: el día del cambio le da el nombre `api` en esa red.
- `odoo.conf.example` y `.env.odoo.example`: se copian sin `.example` en el VPS. Las claves
  maestras, los tokens y las contraseñas van solo en esas copias, nunca en Git ni en la imagen.
- `nginx/odoo.conf`: bloque para el nginx del sistema anterior, con límites de peticiones en
  formularios, ingreso y webhook. La API de n8n no se expone a internet.
- `respaldo.sh` y `restaurar.sh`.

## Para subir al VPS

En `/opt/mirabilenet-odoo`:

- el contenido de `deploy/`;
- `custom_addons/` (sin su carpeta `graphify-out/`);
- de `oca/`: `contract`, `event`, `mis-builder`, `reporting-engine`, `server-ux`,
  `geospatial` (mapa de fibra) y `web` (solo `web_dark_mode`, modo oscuro). Son los mismos de
  `addons_path` en `odoo.conf.example`. Actualizado el 22/11/2026.

No se suben: `env/`, `odoo.conf` de desarrollo, `graphify-out/`, `Static/Datos/` (datos de
clientes: se cargan con los asistentes de importación en el servidor) ni ningún volcado.
