## Pendiente de validar o de hacer

- **Nada se probó contra un MikroTik real.** El cliente de RouterOS tampoco se había probado
  contra equipos en el sistema anterior. Antes de producción: laboratorio con un router de
  prueba para el enrolamiento completo y para cada orden (activar, suspender, corte parcial).
- **El servicio del servidor que aplica los peers de WireGuard** (`mn-wg-sync`) no es parte de
  este módulo: sigue siendo el del sistema anterior y se revisa en la fase 10.
- **El punto público de enrolamiento no limita intentos por IP** (el sistema anterior permitía
  30 por hora). Se resuelve en el proxy del servidor (nginx) en la fase 10.
- **Cortes automáticos por mora y reactivación al pagar**: dependen de los cargos, fase 4.
  El prorrateo del alta prepaga tiene su punto de enganche (`_mirabilenet_on_activated`).
- **Importador de la cartera desde el router** y los datos de cartera importados
  (`ServiceRosterData`): fase 9, con la migración de datos.
- **Contrato del cliente** (`Contract`) y **saldo pendiente**: fase 4.
- **Prospectos de la web** como `crm.lead`: fase 7.
- El módulo `queue_job` de la OCA no se usó: las órdenes las ejecuta una tarea programada de
  Odoo que se dispara al instante, con los reintentos en la propia orden.
- Las pantallas no se probaron en el navegador, solo con pruebas automáticas.
