## Operaciones

- **Nota de crédito**: botón «Nota de crédito» de Odoo sobre una factura ya
  aceptada, publicar y **Emitir al SIAT**.
- **Contingencia en curso**: Contingencias > nuevo evento «en curso» > iniciar.
  Al volver la conexión: cerrar, registrar, enviar y validar paquetes.
- **Facturas en papel (CAFC)**: registrar el talonario, abrir un evento de
  «regularización» con ese talonario y el periodo, y transcribir cada factura
  marcando «Factura manual de contingencia» en la venta.
- **Fecha anterior**: abrir una autorización (máx. 48 h), un evento de
  regularización sin talonario, e indicar la fecha en la venta.

## Pruebas

```
odoo-bin -c odoo.conf -d <base_de_prueba> -i mira_sale_siat --test-tags mira_siat --stop-after-init
```
