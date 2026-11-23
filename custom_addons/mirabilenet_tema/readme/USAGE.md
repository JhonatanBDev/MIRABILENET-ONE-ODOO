No hay nada que configurar: al instalar el módulo toda la parte interna toma los colores.

Para cambiar un color, editar `static/src/scss/primary_variables.scss` (modo claro) o
`primary_variables.dark.scss` (modo oscuro) y actualizar el módulo:

    env\Scripts\python.exe odoo-bin -c odoo.conf -d <base> -u mirabilenet_tema --stop-after-init

Si el navegador sigue mostrando los colores anteriores, recargar con Ctrl+F5.
