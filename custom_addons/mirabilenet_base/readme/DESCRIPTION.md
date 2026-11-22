Fase 1 de la migración de MIRABILENET ONE a Odoo 19. Es la base de los demás módulos
`mirabilenet_*`: define las regiones y el aislamiento entre ellas.

## Qué trae

| Modelo | Qué es |
|---|---|
| `mirabilenet.region` | Región, con su calendario de cobro y su direccionamiento |
| `mirabilenet.branch` | Sucursal de una región |
| `mirabilenet.zone` | Zona de una región |
| `mirabilenet.node` | Nodo de una zona, con su capacidad instalada |
| `mirabilenet.audit.log` | Registro inmutable de acciones críticas |
| `res.users` (extendido) | Rol, región y sucursal del usuario |

Reutiliza de Odoo: empresas, usuarios, grupos, reglas de registro y el historial de `mail`.

## Roles

El campo **Rol en MIRABILENET** del usuario decide sus grupos; no se marcan a mano.

| Rol | Ve | Puede |
|---|---|---|
| Superadministrador, Gerencia | Todas las regiones | Editar regiones, organización y usuarios |
| Auditor | Todas las regiones | Solo leer |
| Administrador regional | Su región | Editar sucursales, zonas, nodos y usuarios de su región |
| NOC, Técnico, Finanzas, Cajero, Cobrador, Almacenista, Vendedor, Operador de cámaras | Su región | Leer la organización |
| Pasante | Nada de la organización | — |

## Reglas que las pruebas sostienen

- Un usuario regional no lee ni escribe registros de otra región, tampoco pidiéndolos por id,
  ni puede mover un registro suyo a otra región.
- Un usuario sin región y sin alcance global no ve nada.
- El auditor lee todo y no modifica nada.
- Solo superadministrador, gerencia y administrador regional administran usuarios.
- Solo el superadministrador otorga roles globales o modifica a quien los tiene.
- El administrador regional solo crea y toca usuarios de su región, y nunca sin región.
- Nadie se edita a sí mismo desde la administración de usuarios.
- Desde esa administración no se pueden asignar grupos: los permisos salen del rol.
- Los usuarios con rol se desactivan, no se eliminan. Las regiones tampoco se eliminan.
- Los cambios de rol, región o estado quedan en la auditoría, que no se edita ni se borra.
