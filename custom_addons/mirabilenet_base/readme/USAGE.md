## Uso

Menú **MIRABILENET**: Organización (regiones, sucursales, zonas, nodos) y Usuarios (lista,
nuevo usuario, auditoría). Tras crear un usuario, «Enviar invitación» le manda el correo para
que defina su contraseña; requiere un servidor de correo configurado.

## Pruebas

```
odoo-bin -c odoo.conf -d <base_de_prueba> -i mirabilenet_base --test-tags mirabilenet --stop-after-init
```
