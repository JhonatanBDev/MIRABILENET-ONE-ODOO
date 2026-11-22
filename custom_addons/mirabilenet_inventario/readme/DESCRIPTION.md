Fase 5 de la migración de MIRABILENET ONE a Odoo 19. El inventario es el de Odoo (`stock`);
este módulo agrega solo lo que `stock` no trae.

## Equivalencias: dónde quedó cada cosa

| Sistema actual | En Odoo |
|---|---|
| `Warehouse` | `stock.warehouse` + sucursal, región y responsable |
| `Warehouse.code`, `nombre`, `activo` | `code`, `name`, `active` |
| `InventoryItem` | `product.template` con «Controlar inventario» |
| `sku` | `default_code` (referencia interna) |
| `categoria` | `categ_id`: las 17 categorías vienen cargadas |
| `marca`, `modelo` | `mirabilenet_brand`, `mirabilenet_model` (nuevos) |
| `descripcion` | `name` |
| `serializado` | `tracking` = por número de serie / sin seguimiento |
| `unidad` | `uom_id` |
| `costo`, `precio_venta` | `standard_price`, `list_price` |
| `stock_minimo` | `mirabilenet_stock_min` (nuevo), con el aviso «bajo el mínimo» |
| `InventorySerial` | `stock.lot` |
| `serial` | `name` |
| `mac`, `proveedor`, `fecha_compra`, `garantia_hasta`, `costo` | Campos nuevos `mirabilenet_*` en la serie |
| `estado`, `region`, `warehouse`, `tecnico`, `customer` | Campos nuevos `mirabilenet_*`, que solo cambian los movimientos |
| `observaciones` | `note` |
| `InventoryStock` | `stock.quant`: Odoo lleva las existencias por ubicación |
| `InventoryMovement` | `stock.move` + tipo, técnico, cliente, documento, motivo y quién lo registró |
| Función `mover()` | `stock.move._mirabilenet_move(...)` |

## Lo único que se programó

1. **La región** del almacén y, a partir de ella, de existencias, series y movimientos, con sus
   reglas de registro.
2. **Los nueve tipos de movimiento** del sistema actual, sobre movimientos reales de Odoo:

   | Tipo | De | A |
   |---|---|---|
   | Compra | Proveedores | Depósito del almacén destino |
   | Salida a técnico | Depósito | «Con técnicos» del almacén |
   | Transferencia | Depósito origen | Depósito destino |
   | Asignación a cliente | Donde esté (depósito o técnico) | Clientes |
   | Devolución | Donde esté (cliente, técnico, reparación) | Depósito destino |
   | Envío a reparación | Donde esté | «En reparación» del almacén |
   | Baja | Donde esté | Baja de equipos |
   | Consumo (a granel) | Depósito | Consumo de material |
   | Ajuste (a granel) | Ajuste por conteo | Depósito, o al revés |

3. **La situación de cada serie** (en almacén, con técnico, en cliente, en reparación, de baja)
   y quién la tiene.

## Reglas que las pruebas sostienen

- Un artículo serializado exige su número de serie; la compra crea la serie y no admite una
  repetida. Una serie dada de baja ya no se mueve.
- El material a granel no sale si no hay existencia suficiente; el ajuste es la excepción.
  Un movimiento rechazado no cambia nada.
- La situación de una serie no se edita a mano: la fijan los movimientos.
- Un movimiento hecho no se edita ni se borra: se revierte con otro. Queda en la auditoría con
  quién lo registró.
- Un usuario regional solo ve y mueve lo de su región, también pidiéndolo por id. No puede
  transferir a un almacén de otra región ni asignar un equipo a un cliente de otra región.
- El auditor lee todo y no modifica nada. El pasante no ve inventario.

## Quién hace qué

| Acción | Roles |
|---|---|
| Almacenes y artículos | Superadministrador, administrador regional, almacenista |
| Movimientos y datos de la serie | Los anteriores, más técnico |
| Leer | Todo el personal de la región; gerencia y auditor, todas |
