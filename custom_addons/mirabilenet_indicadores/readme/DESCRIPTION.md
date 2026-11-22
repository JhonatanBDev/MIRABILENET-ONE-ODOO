Fase 8. Casi todo son datos; el único código propio es la alerta de objetivo de MRR.

## De dónde sale cada indicador

| Indicador | Herramienta |
|---|---|
| Facturación, ventas, caja, cursos, tienda, almacén | Tableros nativos de Odoo (`spreadsheet_dashboard_*`), en MIRABILENET > Indicadores > Tableros de Odoo |
| Por mes, en los últimos 6 meses: facturado, cobrado, tasa de recaudación, pendiente, servicios facturados, ARPU, altas, bajas y avisos de WhatsApp enviados | Informe `mis_builder` (OCA): «Cobranza y servicios por mes». Exporta a Excel y PDF |
| Servicios por región y estado, con la suma de la mensualidad (MRR de activos y morosos) | Gráfico y tabla dinámica nativos |
| Mora de más de 30 días por región y cliente | Gráfico y tabla dinámica sobre facturas vencidas hace más de 30 días |
| Routers por región y estado | Gráfico y tabla dinámica |
| Avisos de WhatsApp por región y estado | Gráfico y tabla dinámica, solo enviados, entregados o leídos |
| Objetivo de MRR por región: MRR actual, capacidad, techo, clientes necesarios y si es alcanzable | Lista con la lectura escrita; sin objetivo o sin precio muestra «—» y el motivo |

## Reglas de la guía

- **Región:** todo se calcula con los permisos de quien mira, así que valen las reglas de región
  que ya tienen facturas, pagos, servicios, routers y mensajes. Los roles globales ven todo.
- **Sin datos no es 0:** en el informe mensual, un mes sin facturas deja la celda vacía (las
  fórmulas devuelven el «sin valor» de `mis_builder`). En las vistas nativas, sin datos se ve
  «—» con el motivo. Las cantidades de altas, bajas y avisos sí pueden ser 0: es un dato.
- **Mensajes y dinero no se mezclan:** los avisos van en su propia fila y su propia vista, como
  cantidad.
- **Solo cuenta lo enviado:** estados enviado, entregado o leído.
