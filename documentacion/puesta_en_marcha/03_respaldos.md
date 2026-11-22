# Respaldos de Odoo

Fase 10, punto 4. Scripts en `deploy/`: `respaldo.sh` y `restaurar.sh`.

## Qué se respalda

- La base de datos, con `pg_dump` en formato propio (`.dump`).
- Los archivos adjuntos (`filestore`): comprobantes, imágenes, entregas de pasantías. Sin ellos
  la base restaurada tiene registros apuntando a archivos que no existen.

`respaldo.sh` comprueba que los dos se pueden leer antes de subirlos.

## Dónde

**Fuera del servidor**, con `rclone`, en el destino de `RCLONE_DESTINO` (Backblaze B2, Google
Drive o cualquier destino de rclone). En el VPS quedan los últimos 14 días.

Programación sugerida (cron del VPS, 3:15 de la mañana):

```
15 3 * * * cd /opt/mirabilenet-odoo && RCLONE_DESTINO=b2:mirabilenet-respaldos ./respaldo.sh >> respaldos/respaldo.log 2>&1
```

## Cómo se restaura

Siempre en una base **nueva**: el script se niega a escribir encima de una existente.

```
./restaurar.sh respaldos/mirabilenet-20261201-0315.dump respaldos/mirabilenet-20261201-0315-filestore.tar.gz mirabilenet_prueba
```

Después: entrar con esa base, revisar módulos, últimas facturas y un adjunto. Para ponerla en
uso, cambiar `db_name` y `dbfilter` en `odoo.conf` y reiniciar Odoo (con confirmación).

## Prueba de restauración

- **20/11/2026, en el equipo de desarrollo:** respaldo de `mira_nativo_test`, restauración en
  una base nueva y comparación de módulos instalados, adjuntos, facturas, regiones y usuarios:
  **iguales**. La copia se borró después. Lo hizo el guion de prueba de la sesión, con
  `pg_dump` y `pg_restore` locales.
- **Pendiente en el VPS:** correr `respaldo.sh` y `restaurar.sh` reales (Docker y rclone) antes
  de la región piloto, y anotar aquí el resultado.

## Claves maestras

No van en el respaldo de la base: viven en `.env.odoo`. Sin `MIRABILENET_MASTER_KEY` y
`MIRA_SIAT_MASTER_KEY`, una base restaurada no puede leer las contraseñas de routers ni el
token del SIN. Respaldarlas aparte, fuera del servidor (claves_maestras.md).
