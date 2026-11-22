# Cómo cambiar el icono y el banner del módulo

Los dos archivos viven en `custom_addons/mira_sale_siat/static/description/`:

| Archivo | Para qué sirve | Dónde se ve |
|---|---|---|
| `icon.png` | Icono del módulo | Lista de Aplicaciones de tu Odoo |
| `banner.png` | Imagen de portada | Tienda de aplicaciones de Odoo (no dentro de tu instancia) |

## Cambiar el icono

1. Prepara la imagen nueva en PNG, cuadrada. Odoo recomienda 256 × 256 px
   (como mínimo 128 × 128).
2. Guárdala como `static/description/icon.png`, reemplazando la anterior.
   - El nombre y la carpeta deben ser exactamente esos: `icon.png` dentro de
     `static/description` (en inglés, no `descripcion`).
   - No hay que tocar `__manifest__.py`: Odoo detecta el icono por la ruta.
3. Aplica el cambio (ver «Aplicar los cambios»).

## Cambiar el banner

1. Prepara la imagen nueva en PNG. El tamaño habitual para la tienda es
   560 × 280 px.
2. Guárdala como `static/description/banner.png`, reemplazando la anterior.
3. Si mantienes el nombre `banner.png`, no hay nada más que hacer.
   Si usas otro nombre, actualiza esta línea de `__manifest__.py`:

   ```python
   "images": ["static/description/banner.png"],
   ```

   La clave es `images` (plural) y su valor es una lista. La primera imagen
   de la lista es la portada.

## Aplicar los cambios

Elige una de las dos formas:

- **Desde la interfaz:** activa el modo desarrollador, entra a
  *Aplicaciones* > *Actualizar lista de aplicaciones* y luego actualiza el
  módulo desde su ficha.
- **Desde la terminal** (en la raíz del repositorio):

  ```
  env\Scripts\python.exe odoo-bin -c odoo.conf -d <tu_base> -u mira_sale_siat --stop-after-init
  ```

Después recarga el navegador sin caché (`Ctrl + F5`).

## Si no se ve el cambio

- **Sigue saliendo el icono viejo:** es la caché del navegador. Recarga con
  `Ctrl + F5` o prueba en una ventana privada.
- **Sale el icono genérico de Odoo:** revisa el nombre (`icon.png`, en
  minúsculas) y la carpeta (`static/description`).
- **El archivo no es un PNG real:** renombrar un `.jpg` a `.png` no basta;
  expórtalo como PNG desde el editor de imágenes.
- **El banner no aparece en tu Odoo:** es normal, solo se muestra en la
  tienda de aplicaciones.
