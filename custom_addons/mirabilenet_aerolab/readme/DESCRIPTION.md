Los cursos de drones son **eventos** de Odoo (`website_event_sale`). La página del curso, el
formulario de inscripción, las entradas con precio, el carrito y el cobro son los de Odoo. El
cupo mínimo para abrir un grupo viene del módulo OCA `event_min_seat`.

Sustituyó al módulo propio anterior, apartado en `retirados/mirabilenet_aerolab_propio`.

## Lo que añade

- **Curso en preparación.** Un curso no se publica en el sitio hasta tener fecha confirmada,
  cupo y una entrada con precio. Odoo pide una fecha a todo evento, por eso existe la casilla
  «Fecha confirmada»: mientras no esté marcada, la fecha es provisional y el curso no sale.
  El formulario dice qué falta.
- **Carnet único por curso.** Toda inscripción pide «Carnet de identidad» (una pregunta de
  Odoo, obligatoria y activa por defecto). El mismo carnet no se inscribe dos veces al mismo
  curso; una inscripción cancelada libera el carnet.
- **Nivel y aplicación** son etiquetas de eventos (Básico, Intermedio…; Pilotaje,
  Fotogrametría…), visibles en el sitio.
- **Región.** Cursos e inscripciones se ven solo en la región del usuario interno; el público
  ve todos los cursos publicados.
- **Permisos** con los grupos de Eventos: gerencia y administración regional administran;
  ventas gestiona inscripciones.
- **Cursos de partida.** Eventos > Configuración > «Cargar cursos de partida de AeroLab» crea
  los cuatro cursos del sistema anterior, sin publicar y sin fecha confirmada, cupo ni precio.

## Lo que cambió respecto al módulo anterior

- **No hay lista de espera.** Con el cupo lleno, Odoo marca el curso como agotado. OCA no tiene
  un módulo para la 19 que la agregue.
- **El pago pasa por la tienda en línea.** Con una entrada con precio, la inscripción va al
  carrito y se confirma al pagar. Para cobrar en efectivo o por transferencia se activa el
  método «Transferencia bancaria» (o uno manual) en Sitio web > Configuración > Pagos.
- **Preguntas del formulario.** Los antiguos interruptores (ocupación, experiencia, drone
  propio…) son ahora preguntas de evento: se agregan o quitan desde el curso.
- **No se valida la edad mínima:** Odoo no tiene preguntas de tipo fecha.
- La presentación de AeroLab, la sede y los requisitos generales se escriben con el editor del
  sitio web.
