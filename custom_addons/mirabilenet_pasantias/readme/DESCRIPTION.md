Las pasantías con **Proyecto** y **Empleados** de Odoo. Sustituyó al módulo propio anterior,
apartado en `retirados/mirabilenet_pasantias_propio`.

## Cómo se arma

| Necesidad | Dónde en Odoo |
|---|---|
| El pasante y su ficha | Empleado de tipo «Practicante», con su tutor como «Coach». Se añaden institución, carrera y horas comprometidas |
| Asistencia | Asistencias de Odoo |
| Proyecto de pasantías | Proyecto con la casilla «Proyecto de pasantías» (visibilidad «usuarios invitados») |
| La tarea de un pasante | Una tarea por pasante, asignada a él |
| La lista de puntos | Las subtareas de esa tarea; cada una dice si es obligatoria |
| Archivos | Adjuntos de la tarea |
| Comentarios | El chat de la tarea |
| Etapas | Por hacer, En curso, Entregada en revisión, Aprobada |
| Informe de avance | Ficha propia ligada a la tarea, con su PDF descargable |

Para dar la misma tarea a varios pasantes, el tutor la duplica (las subtareas se copian) y
cambia el asignado.

## Reglas

1. **Solo ve lo suyo**, y solo lo publicado: «Publicada» en la tarea. Asignar no es publicar;
   mientras no lo esté, no la ve.
2. **No se aprueba a sí mismo.** La etapa y el estado se mueven con «Entregar» y «Revisar la
   entrega»; escribirlos se rechaza. Nadie revisa su propio trabajo.
3. **No entrega a medias:** si faltan subtareas obligatorias, archivos o secciones del informe
   (cuando la tarea los pide), la entrega se rechaza diciendo cuáles.
4. **No crea tareas ni se asigna trabajo.** Solo marca como hechos sus puntos.
5. **No borra archivos de una tarea aprobada**, ni cambia nada más en ella.

Además:

- **Trabajo del equipo:** el pasante ve las tareas ya entregadas o aprobadas de los compañeros
  de su proyecto, con sus archivos, sin poder cambiarlas. El informe y la devolución del tutor
  no se comparten.
- Pedir cambios exige decir cuáles; reabrir una tarea aprobada pide confirmación. La
  devolución queda en el informe y se avisa al pasante.
- **Archivos:** lista de extensiones permitidas, sin `.html`, `.htm` ni `.svg`; hasta 90 MB.
- Tutores: superadministrador, gerencia, administración regional, NOC y técnico (gestionan
  proyectos). Cada tutor ve los proyectos de su región.
- Entregas y revisiones quedan en la auditoría.

## Lo que cambió respecto al módulo anterior

- Ya no se asigna una tarea a varios pasantes de una vez: una tarea por pasante.
- Se perdió la separación entre la «nota del pasante» y el hilo: todo va al chat de la tarea.
- Sin aviso por WhatsApp (decidido el 20/11/2026).
