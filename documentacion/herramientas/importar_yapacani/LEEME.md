# Importar la cartera de Yapacaní

> **Desde el 22/11/2026 esto se hace desde Odoo:** MIRABILENET > Importar cartera (módulo
> `mirabilenet_cartera`), con las mismas reglas. Estos scripts quedan como referencia.

Importa `Static/Datos/datosyapacani_completo.csv` (planilla de clientes de Yapacaní) a Odoo.
Se hizo el 22/11/2026 en `mira_nativo_test`: 37 planes, 184 clientes, 188 servicios activos,
188 cuentas PPPoE y 173 ONU, sin errores.

1. **Limpiar** (no toca la planilla original):
   `py -3.10 documentacion\herramientas\importar_yapacani\limpiar.py`
   Deja `Static/Datos/datosyapacani_limpio.csv` (lista para importar) y
   `Static/Datos/datosyapacani_revisar_en_campo.csv` (lo que no se pudo deducir).
2. **Importar** (necesita la región con código `YAP`; repetirlo no duplica nada):
   `env\Scripts\python.exe odoo-bin shell -c odoo.conf -d <base> --no-http < documentacion\herramientas\importar_yapacani\importar.py`

Qué crea y cómo:

- **Planes:** uno por perfil de Winbox, con el perfil exacto en «Perfil PPP», la velocidad del
  nombre (bajada = subida) y el precio de la planilla. CATV = incluye TV. Código `YAP-<perfil>`.
- **Clientes:** uno por persona (mismo C.I. y mismo nombre); residencial, activo, C.I. en el
  campo NIT/CI, barrio en la segunda línea de la dirección, coordenadas de la planilla.
- **Servicios:** activos, prepago, precio y fecha de alta de la planilla, **sin órdenes a los
  routers** y **sin contrato de cobro** (se crea cuando se decida la fecha de inicio del cobro).
- **Cuentas PPPoE:** usuario, IP fija y perfil. Sin contraseña (la planilla no la trae).
- **ONU:** un producto por marca y modelo, y cada serie como número de serie instalado en el
  cliente, con su MAC. Una serie repetida en varias filas se registra una sola vez.
