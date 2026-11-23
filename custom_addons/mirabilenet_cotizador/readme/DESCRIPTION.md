Cotizaciones de CCTV y redes con el motor del Cotizador DigiCorp (`referencia/`), como otra línea
de venta de MIRABILENET.

- **Motor**, en Python puro en `cotizador/` y traído del programa original: precios, cálculo de
  disco, lector de pedidos, selección de equipos y armado de kits.
  - El recargo sobre el costo del proveedor se elige en este orden: escalón por costo para ítems
    baratos, subcategoría, categoría y, si nada aplica, el recargo por defecto. Hay topes.
  - Redondeo comercial: múltiplos de 5 Bs, o de 0,50 por debajo de 50 Bs.
  - IVA 13 % + IT 3 %, que se agregan (×1,16) o se toman incluidos («bruto»).
  - Disco del NVR según megapíxeles, días, códec y modo de grabación.
  - La selección exige stock en la ciudad (sin contar el showroom) y prefiere las marcas
    preferidas.
- **Cotización = venta de Odoo** con:
  - etapas (borrador, aprobada, enviada, ganada o perdida) y número COT-AAAA-NNNN;
  - vigencia;
  - tipo de cambio congelado;
  - secciones (equipos, materiales, mano de obra, viáticos).
  - **Los precios no cambian** al abrirla, al cambiar la cantidad ni al duplicarla. Solo cambian
    si se toca el recargo a mano, dentro de los topes.
- **Nueva cotización:** desde un kit, o desde el pedido escrito («6 cámaras para mi tienda,
  2 afuera, 20 días»). El texto se interpreta por reglas; los precios y los productos los pone el
  motor.
- **PDF para el cliente**, con marca «BORRADOR» si no está aprobada. **Nunca** lleva costo,
  recargo, ganancia, stock, alertas ni notas internas (lo verifica una prueba).
- **Catálogo:** productos con categoría del proveedor, precio de venta, precio con factura y stock
  del proveedor.
- **Configuración:** recargos, kits, materiales, mano de obra y ciudades con viáticos.
- **Quién aprueba:** quien cotiza aprueba y envía (decisión de MIRABILENET).
