#!/bin/sh
# Restaura un respaldo en una base NUEVA (nunca encima de la que está en uso).
# Uso:  ./restaurar.sh respaldos/mirabilenet-AAAAMMDD-HHMM.dump respaldos/...-filestore.tar.gz mirabilenet_prueba
# Para volver a producción con un respaldo, restaurar en una base nueva, comprobarla y
# después cambiar db_name y dbfilter en odoo.conf (con confirmación).
set -eu
DUMP="${1:?Falta el archivo .dump}"
FILES="${2:?Falta el archivo de filestore}"
NUEVA="${3:?Falta el nombre de la base nueva}"
ORIGEN="$(basename "$DUMP" | sed 's/-[0-9]\{8\}-[0-9]\{4\}\.dump$//')"

if docker compose exec -T odoo_db sh -c 'psql -U $POSTGRES_USER -lqt' | cut -d'|' -f1 | grep -qw "$NUEVA"; then
    echo "La base $NUEVA ya existe: elija otro nombre." >&2
    exit 1
fi
docker compose exec -T odoo_db sh -c "createdb -U \$POSTGRES_USER $NUEVA"
docker compose exec -T odoo_db sh -c "pg_restore -U \$POSTGRES_USER -d $NUEVA --no-owner /respaldos/$(basename "$DUMP")"
docker compose run --rm --no-deps -v "$(pwd)/respaldos:/entrada" --entrypoint sh odoo -c \
    "mkdir -p /var/lib/odoo/filestore/$NUEVA && tar -xzf /entrada/$(basename "$FILES") -C /tmp && cp -a /tmp/$ORIGEN/. /var/lib/odoo/filestore/$NUEVA/"
echo "Restaurado en $NUEVA. Comprobar: módulos instalados, últimas facturas y adjuntos."
