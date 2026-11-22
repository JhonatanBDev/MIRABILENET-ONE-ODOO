Fases 2 y 3 de la migración de MIRABILENET ONE a Odoo 19: clientes, planes, servicios, cuentas
PPPoE, routers MikroTik, subredes y órdenes de red.

## Arquitectura

```
mirabilenet.service  ->  mirabilenet.service.transition  (orden de red)
                                   |
                         isp/gateway.py  RouterGateway        <- única puerta a los equipos
                                   |-- RealRouterGateway -> isp/routeros.py -> MikroTik
                                   `-- FakeRouterGateway (doble para desarrollo y pruebas)
```

La carpeta `isp/` no importa Odoo: direccionamiento, guiones RouterOS, peers de WireGuard,
cifrado y la puerta hacia los routers se prueban aislados.

## Qué reutiliza y qué agrega

| Del sistema actual | En Odoo |
|---|---|
| `Customer`, `CustomerContact` | `res.partner` y sus contactos, con campos por herencia |
| `Plan` | `product.template` de tipo servicio, con campos por herencia |
| `Service` | `mirabilenet.service` (nuevo) |
| `PPPoEAccount` | `mirabilenet.pppoe.account` (nuevo) |
| `ServiceStateTransition` | `mirabilenet.service.transition` (nuevo) |
| `Router`, `EnrollmentToken`, `RouterConfigChange` | `mirabilenet.router`, `.enrollment.token`, `.router.config.change` (nuevos) |
| `NetworkSubnet` | `mirabilenet.subnet` (nuevo) |
| `routeros.py` y las plantillas de `enrollment.py` | Copiados sin cambios a `isp/` |

No se encontró en Odoo ni se usó ningún módulo de terceros para la red.

## Reglas que las pruebas sostienen

Clientes y planes: ver la sección de la fase 2 más abajo.

Servicios:

- El estado del servicio **no se edita**: cambia solo cuando el equipo confirma la orden.
- Una orden que falla se reintenta; al tercer intento queda en «revisión manual» y el servicio
  sigue como estaba. Desde ahí alguien la reintenta o la cancela.
- Las órdenes se ejecutan en una tarea programada, nunca dentro de la petición del usuario.
- Pedir dos veces la misma orden con la misma clave no la duplica.
- La modalidad de pago (prepago o pospago) va en el servicio, no en el cliente.
- El precio mensual se copia del plan al contratar y admite un valor propio; cambiar de plan no
  lo cambia solo.
- Servicio, plan, router y nodo son de la región del cliente.
- Un plan con servicios, aunque estén de baja, no se elimina.
- Un servicio no se elimina: se da de baja.
- Dan órdenes: superadministrador, administrador regional, NOC y técnico.

Routers y enrolamiento:

- La IP de gestión la asigna la plataforma: `10.250.<región × 10>.<host>`.
- Un router solo pasa a «Conectado» con los cinco chequeos en verde (handshake, ping, API,
  identidad y versión). El handshake solo lo deja «Degradado».
- El código de enrolamiento sirve una vez, vence a los 15 minutos y solo hay uno vigente por
  router. Los intentos con códigos inválidos quedan en la auditoría.
- Las plantillas RouterOS son las revisadas del sistema anterior; una prueba falla si cambian.
- Un peer de WireGuard nunca lleva `0.0.0.0/0`.
- Los datos que fija el enrolamiento o el diagnóstico no se editan desde un formulario.
- Administran routers y subredes: superadministrador, administrador regional y NOC.

Subredes:

- La red no se elige: se reserva la siguiente libre, `10.<64 + región>.<sitio>.0/24`, con la
  región bloqueada para que dos operadores nunca reciban la misma.
- Al liberarla pasa 30 días en cuarentena antes de poder reutilizarse.

Secretos: las contraseñas de la API y de PPPoE se guardan cifradas y no se muestran ni se
devuelven. El código de enrolamiento tampoco se puede leer desde la interfaz.

Todo lo anterior está aislado por región, también pidiendo un registro por su id, y el pasante
no ve nada de la red.

## Fase 2: clientes y planes

Campos de Odoo que se usan tal cual: `vat` (documento o NIT), `phone`, `email`, `street`,
`partner_latitude` / `partner_longitude`, `user_id` (vendedor), `comment`, `list_price` (precio
mensual) y `active`. Los datos fiscales del cliente están en `mira_sale_siat`; este módulo no
depende de él.

Clientes:

- Un usuario regional solo ve y modifica clientes de su región. Los contactos de un cliente
  siguen la misma regla. Lo que no es cliente (proveedores, usuarios) se sigue viendo.
- Crean y modifican clientes: superadministrador, gerencia, administrador regional, vendedor y
  finanzas. Quien atiende servicios (técnico, NOC) mantiene los contactos de un cliente, pero
  no al cliente.
- Todo cliente pertenece a una región; su zona y su sucursal son de esa región.
- El código (`CLI-00001`) se asigna solo y no se repite.
- El estado comercial cambia solo con los botones y solo por las transiciones permitidas.
  Un cliente nuevo nace como prospecto.

Planes:

- «Activo» y «Publicar en la web» son decisiones distintas. Un plan está publicado solo si está
  activo, marcado para publicar y con precio mayor que cero. «Publicar» nace apagado.
- Cada región ve sus planes y los que valen en todas las regiones.
- Solo gerencia y administración regional crean o modifican planes.
- Un plan que vale en todas las regiones solo lo elimina un usuario con alcance global.
