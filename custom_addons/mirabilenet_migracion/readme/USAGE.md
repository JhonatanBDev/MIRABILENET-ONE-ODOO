## Cómo se corre

Nunca contra producción. Primero sobre una base de Odoo de prueba, después sobre la definitiva.

```powershell
$env:MIRABILENET_ORIGEN_DSN = "dbname=copia_mirabilenet host=localhost user=... password=..."
$env:MIRABILENET_INICIO_COBRO = "2026-12-01"   # desde cuándo factura Odoo
env\Scripts\python.exe odoo-bin shell -c odoo.conf -d <base_odoo> < custom_addons\mirabilenet_migracion\scripts\migrar.py
```

Archivos: comprobantes, imágenes, QR y entregas de pasantías no están en la base, sino en las
carpetas `media` y `private_media` del sistema anterior. Se indican con
`MIRABILENET_ORIGEN_MEDIA` y `MIRABILENET_ORIGEN_PRIVADO` (copias de esas carpetas). Sin ellas,
lo que necesita un archivo se rechaza y, si es un comprobante, la migración se detiene.

Opcionales: `MIRABILENET_ORIGEN_ESQUEMA` (por defecto `public`), `MIRABILENET_ETAPAS` (por
ejemplo `organization,users`) y `MIRABILENET_INFORME` (ruta del informe en Markdown). Una corrida
parcial solo comprueba las sumas de las etapas que corrió.

El origen se abre en solo lectura. Si una suma de control no coincide, se deshace todo y se
muestran la diferencia y los rechazados.
