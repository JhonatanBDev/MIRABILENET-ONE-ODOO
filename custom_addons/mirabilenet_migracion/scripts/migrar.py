"""Corre la migración. Se ejecuta con la consola de Odoo, nunca contra producción:

    set MIRABILENET_ORIGEN_DSN=dbname=copia_mirabilenet host=localhost user=... password=...
    env\Scripts\python.exe odoo-bin shell -c odoo.conf -d <base_odoo> < custom_addons\mirabilenet_migracion\scripts\migrar.py

Variables opcionales: MIRABILENET_ORIGEN_ESQUEMA (por defecto public), MIRABILENET_ETAPAS
(lista separada por comas; por defecto todas), MIRABILENET_INFORME (ruta del informe) y
MIRABILENET_INICIO_COBRO (AAAA-MM-DD: desde cuándo factura Odoo los servicios vigentes),
MIRABILENET_ORIGEN_MEDIA y MIRABILENET_ORIGEN_PRIVADO (copias de las carpetas media y
private_media del sistema anterior, para comprobantes, imágenes y entregas).
El origen se abre en solo lectura. Si una suma de control no coincide, no se guarda nada.
"""
import os

import psycopg2

from odoo.addons.mirabilenet_migracion.migracion.source import SourceReader

dsn = os.environ["MIRABILENET_ORIGEN_DSN"]
schema = os.environ.get("MIRABILENET_ORIGEN_ESQUEMA", "public")
stages = [s for s in os.environ.get("MIRABILENET_ETAPAS", "").split(",") if s] or None
report_path = os.environ.get("MIRABILENET_INFORME", "informe_migracion.md")
billing_start = os.environ.get("MIRABILENET_INICIO_COBRO")  # AAAA-MM-DD, día del cambio
media_root = os.environ.get("MIRABILENET_ORIGEN_MEDIA")      # copia de la carpeta media
private_root = os.environ.get("MIRABILENET_ORIGEN_PRIVADO")  # copia de private_media

source = psycopg2.connect(dsn)
source.set_session(readonly=True)
try:
    Migration = env["mirabilenet.migration"].sudo().with_context(
        mirabilenet_billing_start=billing_start, mirabilenet_media_root=media_root,
        mirabilenet_private_root=private_root)
    try:
        result = Migration._run(SourceReader(source.cursor(), schema), stages=stages)
    except Exception as exc:
        env.cr.rollback()
        print("MIGRACION DETENIDA:", exc)
        raise SystemExit(1)
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write(Migration._report_markdown(result))
    env.cr.commit()
    print("MIGRACION TERMINADA. Informe:", report_path)
finally:
    source.close()
