#!/bin/sh
# Etapas de facturas del SIN (PILOTO), un proceso por punto de venta en paralelo.
# El SIN de pruebas tarda ~30 s por factura recibida: en paralelo se tarda la mitad.
# Uso, en /opt/mirabilenet-odoo:  nohup sh siat_pruebas/cadena_paralela.sh &
# Avance: siat_pruebas/pv0.log y siat_pruebas/pv1.log
cd /opt/mirabilenet-odoo

correr() {  # $1 log, $2 etiqueta, resto: variables -e
  log="$1"; et="$2"; shift 2
  echo "=== $(date +%H:%M:%S) inicio $et" >> "$log"
  docker compose run --rm --no-deps -T "$@" odoo odoo shell -c /etc/odoo/odoo.conf \
    -d mirabilenet --no-http --log-level=warn < siat_pruebas/etapas_facturas.py 2>&1 \
    | grep -v without_demo >> "$log"
}

pv0() {
  L=siat_pruebas/pv0.log
  correr $L "reintentos"  -e SIAT_PV=0 -e SIAT_ETAPA=0
  correr $L "IV"          -e SIAT_PV=0 -e SIAT_ETAPA=4  -e SIAT_CANTIDAD=85
  correr $L "VII"         -e SIAT_PV=0 -e SIAT_ETAPA=7  -e SIAT_CANTIDAD=125
  correr $L "XI"          -e SIAT_PV=0 -e SIAT_ETAPA=11 -e SIAT_CANTIDAD=125
  correr $L "V-VI eventos 1-4 (paquetes chicos)" -e SIAT_PV=0 -e SIAT_ETAPA=5 \
    -e SIAT_EVENTOS=1,2,3,4 -e SIAT_CANTIDAD=10 -e SIAT_FACTURAS_EVENTO=1
  echo "=== $(date +%H:%M:%S) PV0 TERMINADO" >> $L
}

pv1() {
  L=siat_pruebas/pv1.log
  correr $L "IV"          -e SIAT_PV=1 -e SIAT_ETAPA=4  -e SIAT_CANTIDAD=125
  correr $L "VII"         -e SIAT_PV=1 -e SIAT_ETAPA=7  -e SIAT_CANTIDAD=125
  correr $L "XI"          -e SIAT_PV=1 -e SIAT_ETAPA=11 -e SIAT_CANTIDAD=125
  correr $L "V eventos 1-4 (registro)" -e SIAT_PV=1 -e SIAT_ETAPA=5 \
    -e SIAT_EVENTOS=1,2,3,4 -e SIAT_CANTIDAD=5 -e SIAT_FACTURAS_EVENTO=1
  correr $L "VI eventos 1-4 (10 paquetes de 500)" -e SIAT_PV=1 -e SIAT_ETAPA=5 \
    -e SIAT_EVENTOS=1,2,3,4 -e SIAT_CANTIDAD=1 -e SIAT_FACTURAS_EVENTO=5000
  echo "=== $(date +%H:%M:%S) PV1 TERMINADO" >> $L
}

pv0 &
pv1 &
wait
