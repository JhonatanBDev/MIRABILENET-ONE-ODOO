Subsistema fiscal de Mira_Sale para Odoo 19. Habla directamente con el SIAT del
SIN (sin intermediarios) en modalidad **Computarizada en Línea**.

Documentos que emite:

| Documento | Sector | Servicio del SIN |
|---|---|---|
| Factura de Compra y Venta | 1 | `ServicioFacturacionCompraVenta` |
| Factura de Telecomunicaciones | 22 | `ServicioFacturacionTelecomunicaciones` |
| Nota de Crédito-Débito | 24 | `ServicioFacturacionDocumentoAjuste` |

Implementa la especificación *Mira_Sale - Proyecto técnico integral para Sistema
Proveedor de Facturación SIAT* (v1.0). El núcleo comercial (clientes, productos,
ventas, pagos, usuarios) es el de Odoo; este módulo aporta el subsistema SIAT.

## Resumen

- Multiempresa: cada empresa es un contribuyente con su token delegado,
  sucursales, puntos de venta, CUIS, CUFD, catálogos y secuencias aislados.
- SIAT Adapter independiente del ORM (paquete `siat/`): cliente SOAP,
  gateway real y simulador, CUF, XML por documento sector, XSD, empaquetado.
- Documento fiscal con ciclo de vida propio, idempotente y reintentable.
- Anulación, reversión, eventos significativos y envío por paquetes.
- Representación gráfica con QR, evidencia técnica y auditoría append-only.

## Arquitectura

```
account.move (venta / nota)     <- dominio comercial, no conoce el SIAT
      |
mira.siat.invoice               <- orquestador + máquina de estados fiscal
      |
siat/gateway.py  SiatGateway    <- interfaz interna (sin SOAP a la vista)
      |-- RealSiatGateway -> siat/soap_client.py -> SIAT PILOTO / PRODUCCIÓN
      `-- FakeSiatGateway (simulador para desarrollo y pruebas)
```

| Componente | Dónde vive |
|---|---|
| Tenant / perfil tributario | `res.company` (campos `mira_siat_*`) |
| Sucursales, puntos de venta, registro ante el SIN | `mira.siat.branch`, `mira.siat.pos` |
| SiatTokenVault | `siat/vault.py` + `res.company._mira_siat_set_token` |
| SiatSoapClient | `siat/soap_client.py` |
| CUIS / CUFD | `mira.siat.pos._get_cuis/_get_cufd`, `mira.siat.cuis`, `mira.siat.cufd` |
| Catálogos | `mira.siat.catalog._sync` (fecha + huella SHA-256) |
| Métodos de pago combinados | `siat/payment_methods.py` |
| CufGenerator | `siat/cuf.py` |
| XmlBuilder (por sector) | `siat/xml_builder.py` (`@register_sector`) |
| XsdValidator | `siat/xsd_validator.py` + `mira.siat.xsd` |
| Emisión, reintento, anulación, reversión | `mira.siat.invoice` |
| Contingencia, paquetes | `mira.siat.event`, `mira.siat.package` |
| CAFC, fecha anterior | `mira.siat.cafc`, `mira.siat.retro.authorization` |
| Nominatividad y NIT reservados | `res.partner._mira_siat_fiscal_identity` |
| PDF, ticket 80 mm, correo | `report/`, plantillas en `data/` |
| Asistente de configuración | `wizards/mira_siat_config_wizard.py` |
| Auditoría / evidencia | `mira.siat.audit.log`, `mira.siat.log` |

El paquete `siat/` no importa Odoo: se puede probar y reutilizar aislado.

Los XSD (`data/xsd/`) y los WSDL de PILOTO (`data/wsdl/`) son copias de los
artefactos oficiales. Los nombres de operaciones y el orden de los elementos de
cada solicitud SOAP salen de esos WSDL.

## Reglas que el código garantiza

- **Aislamiento**: reglas de registro por empresa en todos los modelos.
- **Sin duplicados**: clave de idempotencia; tras un timeout se consulta el
  estado por CUF y solo se reenvía *el mismo archivo* si el SIN no lo tiene.
- **Número atómico** por punto de venta + sector, reservado con bloqueo de fila.
- **XSD obligatorio**: sin XSD o con XML inválido no se envía nada.
- **Dinero en Decimal**; precios con impuesto incluido y 2 decimales.
- **Nominatividad**: nunca se emite sin documento del comprador; NIT y CI solo
  dígitos; NIT reservados 99001 / 99002 / 99003 con sus reglas.
- **Método de pago**: se deduce de los cobros conciliados (por diario) y del
  plazo; no se declara un cobro inmediato en una venta a crédito sin pagos.
- **Tarjeta**: se guarda y se envía solo enmascarada.
- **Secretos**: token, CUIS y CUFD cifrados con una clave fuera de la base.
- **Inmutabilidad**: documentos fiscales, paquetes, evidencia, auditoría y
  autorizaciones no se editan ni se borran.
