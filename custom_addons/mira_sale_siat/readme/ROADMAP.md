## Pendiente antes de homologar

- Ejecutar los casos de la Fase 1 contra PILOTO con el token y el código de
  sistema reales: el módulo solo se probó contra el simulador.
- Contrastar el CUF con el vector de prueba del SIN.
- Confirmar con el SIN: `tipoFacturaDocumento = 3` para la nota de
  crédito-débito, el código 986 de NIT activo, y las reglas de plazo de los
  eventos significativos con fechas pasadas.
- Volver a descargar XSD (los incluidos son versión 23/08/2021), WSDL y
  catálogos antes de cada homologación.

## Fuera de alcance de esta versión

- Electrónica en Línea (firma XMLDSig): la emisión se bloquea con un mensaje.
- Otros documentos sector; notas sobre facturas en moneda extranjera.
- API REST propia `/api/v1` y panel del proveedor.
- Adaptadores por rubro (abonados y cobro periódico de ISP, restaurante).
