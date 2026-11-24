#!/bin/sh
# Respaldo de Odoo: base (pg_dump) + archivos adjuntos (filestore), copiados FUERA del servidor.
# Uso, desde /opt/mirabilenet-odoo:  ./respaldo.sh
# Programado a diario con cron:      15 3 * * * cd /opt/mirabilenet-odoo && ./respaldo.sh
# Necesita rclone con un destino configurado (RCLONE_DESTINO, p. ej. "b2:mirabilenet-respaldos").
set -eu
DB="${DB:-mirabilenet}"
DESTINO="${RCLONE_DESTINO:?Defina RCLONE_DESTINO con el destino de rclone}"
DIAS="${DIAS_A_CONSERVAR:-14}"
STAMP="$(date +%Y%m%d-%H%M)"
DIR="./respaldos"
mkdir -p "$DIR"

docker compose exec -T odoo_db sh -c "pg_dump -U \$POSTGRES_USER -Fc $DB" > "$DIR/$DB-$STAMP.dump"
docker compose run --rm --no-deps --user 0 -v "$(pwd)/respaldos:/salida" --entrypoint sh odoo \
    -c "tar -czf /salida/$DB-$STAMP-filestore.tar.gz -C /var/lib/odoo/filestore $DB"

# Un respaldo que no se puede leer no es un respaldo: se comprueba antes de subirlo.
docker compose exec -T odoo_db pg_restore --list "/respaldos/$DB-$STAMP.dump" > /dev/null
tar -tzf "$DIR/$DB-$STAMP-filestore.tar.gz" > /dev/null

rclone copy "$DIR/$DB-$STAMP.dump" "$DESTINO/"
rclone copy "$DIR/$DB-$STAMP-filestore.tar.gz" "$DESTINO/"
find "$DIR" -name "$DB-*" -mtime +"$DIAS" -delete
echo "Respaldo $STAMP copiado a $DESTINO"
