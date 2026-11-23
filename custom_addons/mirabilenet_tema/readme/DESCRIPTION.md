Estilo moderno y limpio, con los colores del logo de MIRABILENET, en la parte interna de Odoo.

- Colores: azul noche `#0f172a` (barra superior), azul `#006db7` (botones, enlaces y
  acciones) y celeste `#00abda` (acciones en modo oscuro). Tomados de `Static/LOGO MIRABILENET.png`.
- Esquinas más redondeadas, sombras suaves en la hoja del formulario, en las tarjetas kanban
  y en las ventanas emergentes; cabeceras de lista marcadas y filas resaltadas al pasar el mouse.
- Pantallas de ingreso, registro y cambio de contraseña como una tarjeta centrada.
- Respeta el modo oscuro de OCA `web_dark_mode` y de `mirabilenet_modo_oscuro`: en oscuro
  la barra es más oscura y las acciones usan el celeste.

Solo SCSS sobre las variables de Odoo (`web._assets_primary_variables`): no reemplaza
plantillas ni vistas. El sitio web público toma los mismos colores con la paleta
«mirabilenet» de `mirabilenet_web`.
