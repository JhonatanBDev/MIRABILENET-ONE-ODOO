- **Márgenes reales: no van al repositorio.** En una base nueva, cárguelos desde
  `referencia/config/pricing.yaml`:
  ```
  env\Scripts\python.exe odoo-bin shell -c odoo.conf -d <base> --no-http < documentacion\herramientas\cargar_margenes_cotizador.py
  ```
  También se editan a mano en MIRABILENET > Cotizaciones > Configuración > Recargos.
- **Ajustes del cotizador** (MIRABILENET > Cotizaciones > Configuración > Ajustes):
  - **Cobrar IVA + IT:** interruptor general. Apagado, las cotizaciones nuevas salen sin
    factura ni impuestos; las ya armadas no cambian.
  - Cómo se aplican los impuestos (se suman o ya vienen incluidos) y sus porcentajes.
  - Si se cotiza con factura por defecto, la vigencia y el tipo de cambio manual.
  - **Usuario y contraseña de DigiCorp:** la contraseña se guarda cifrada con
    `MIRABILENET_MASTER_KEY` y no se vuelve a mostrar. Si el servidor tiene las variables de
    entorno `DIGICORP_USER` y `DIGICORP_PASS`, mandan esas.
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
- **PDF:** hace falta wkhtmltopdf 0.12.6. En la PC de desarrollo está en
  `C:\Program Files\wkhtmltopdfin` (`bin_path` en `odoo.conf`). En el VPS ya viene en la
  imagen de Odoo.
