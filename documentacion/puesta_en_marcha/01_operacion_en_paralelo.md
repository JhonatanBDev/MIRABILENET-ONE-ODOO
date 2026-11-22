# Operación en paralelo

Fase 10, punto 1. Plan para pasar del sistema anterior a Odoo **región por región**, con
vuelta atrás en cada paso. Nada de esto se ejecuta en el VPS sin confirmación paso a paso.

## Principios

- **Un solo sistema manda en cada región.** Nunca se emite, cobra ni corta lo mismo en los dos.
- **La red la manda quien manda la región:** solo ese sistema envía órdenes a los routers de
  esa región. Los cortes automáticos del otro quedan apagados para ella.
- **WhatsApp y n8n no se parten por región:** apuntan a un solo sistema. Pasan al final, en un
  día propio (documento 02).

## Etapas

| Etapa | Duración | Sistema anterior | Odoo |
|---|---|---|---|
| 0. Ensayo | 1 semana | Todo, como hoy | Copia de los datos (fase 9) en una base de prueba en el VPS. Se revisan pantallas, informe de migración e indicadores |
| 1. Región piloto | 2 a 4 semanas | Todo menos la región piloto | La región piloto: cobros, caja de sucursal, servicios. Corte automático encendido solo para ella |
| 2. Resto de regiones | 1 región por semana | Lo que falte | Cada región que pasa |
| 3. Mensajería | 1 día | Solo lectura | WhatsApp, n8n y sitio web (documento 02) |
| 4. Cierre | 1 mes | Solo lectura, respaldo final | Todo |

## Qué se hace en cada paso de región

1. Migrar la región. La migración corre por etapas; para una sola región, se filtra la copia
   antes de correrla.
2. Comprobar el informe de control: las sumas tienen que dar igual. Si no, no se sigue.
3. En el sistema anterior, apagar para esa región la emisión de avisos, el corte y la
   reactivación automáticos.
4. En Odoo, encender para esa región el corte y la reactivación (ficha de la región), con
   `MIRABILENET_INICIO_COBRO` en el primer día del período siguiente.
5. Avisar al personal de la región: desde ese día, cobran y registran en Odoo.

## Vuelta atrás de una región

Si algo falla en las primeras dos semanas:

1. En Odoo, apagar corte y reactivación de la región.
2. Registrar en el sistema anterior los pagos que se hicieron en Odoo (lista: Cobros > Pagos,
   filtrado por región y fecha).
3. Volver a encender en el sistema anterior la emisión y los cortes de la región.

Lo que sale del sistema anterior durante el paralelo no vuelve solo: por eso cada región dura
poco y se registra a mano lo que pasó en Odoo.

## Antes de empezar

- [ ] La copia de la base para la fase 9 (la indica el usuario).
- [ ] Revisión de pantallas en el navegador.
- [ ] Prueba de la factura SIAT en el ambiente piloto (si se va a emitir desde el primer día).
- [ ] Laboratorio con un MikroTik real.
- [ ] Claves maestras propias del VPS, respaldadas (claves_maestras.md).
