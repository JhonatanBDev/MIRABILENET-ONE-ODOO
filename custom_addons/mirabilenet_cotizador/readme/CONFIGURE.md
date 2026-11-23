- **Márgenes reales: no van al repositorio.** En una base nueva, cárguelos desde
  `referencia/config/pricing.yaml`:
  ```
  env\Scripts\python.exe odoo-bin shell -c odoo.conf -d <base> --no-http < documentacion\herramientas\cargar_margenes_cotizador.py
  ```
  También se editan a mano en MIRABILENET > Cotizaciones > Configuración > Recargos.
- **Parámetros** (Ajustes técnicos > Parámetros, prefijo `mirabilenet_cotizador.`):
  - `modo_impuestos`: «agregar» si el precio de DigiCorp no trae IVA, o «bruto» si lo trae;
  - `recargo_defecto`;
  - topes de recargo;
  - redondeo;
  - vigencia;
  - tipo de cambio manual;
  - `viaticos_por_km`.
- **Tarifas de mano de obra y viáticos:** las que trae el módulo son de ejemplo. Cámbielas en
  Configuración.
- **Permisos:**
  - «Cotizador: cotizar y enviar» para quien cotiza;
  - «Cotizador: configuración» para quien cambia márgenes y kits (los administradores ya la
    tienen).
- **PDF en esta PC:** hace falta wkhtmltopdf 0.12.6. En el VPS ya viene en la imagen de Odoo.
