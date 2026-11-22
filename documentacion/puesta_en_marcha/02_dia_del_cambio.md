# Día del cambio de mensajería y vuelta atrás

Fase 10, puntos 2 y 3. Es el día en que WhatsApp y n8n pasan de la API del sistema anterior a
Odoo. **Los flujos de n8n no se editan:** siguen llamando a `http://api:8000/...`. Lo que cambia
es a quién responde el nombre `api` dentro de la red de Docker.

Decidido (20/11/2026): **cambio sin listas pendientes de respuesta.** No se conservan los
identificadores viejos de avisos y comprobantes; el cambio se hace cuando no queda ninguna
lista de avisos ni comprobante esperando respuesta del cliente.

## La víspera

- [ ] Respaldo de los dos sistemas (sistema anterior y Odoo), copiado fuera del servidor.
- [ ] Odoo levantado en el VPS (`docker compose up -d`) con los datos migrados, conectado a la
      red del sistema anterior como `odoo`.
- [ ] Mismo token y mismo secreto de firma de n8n en `.env.odoo` que en el sistema anterior
      (`MIRABILENET_N8N_API_TOKEN`, `MIRABILENET_N8N_WEBHOOK_SECRET`).
- [ ] En Odoo, MIRABILENET > Mensajería > Ajustes: número, plantillas y tokens de Meta
      cargados; la dirección del webhook de entrada de n8n, la misma que hoy.
- [ ] Parámetro `mirabilenet.wg_config_dir` = `/wireguard` (Ajustes > Técnico > Parámetros).
- [ ] Las pruebas automáticas de Odoo en verde sobre la base migrada.

## El día (en horario de poco tráfico)

| # | Paso | Comprobación |
|---|---|---|
| 1 | Pausar los avisos automáticos del sistema anterior (beat de Celery) | No salen avisos nuevos |
| 2 | Esperar a que no queden listas de avisos ni comprobantes sin respuesta | Bandeja de conversaciones vacía de pendientes |
| 3 | Quitar el nombre `api` al contenedor del sistema anterior: en su compose, `container_name`/alias de `api` → `api_anterior`, y `docker compose up -d api` | `docker network inspect` ya no muestra `api` en él |
| 4 | Darle el nombre a Odoo: `docker compose -f docker-compose.yml -f docker-compose.cambio.yml up -d odoo` | `docker compose exec n8n wget -qO- http://api:8000/web/health` responde |
| 5 | **Prueba en el simulador** (MIRABILENET > Mensajería > Simulador), con Odoo y el n8n real: flujo 15 (un cliente pide su deuda), 13 (envía un comprobante), 16 (pide una persona) y 17 (un número desconocido pide planes). Si algo falla, se vuelve atrás antes de tocar Meta | Cada flujo responde con datos de Odoo |
| 6 | Agregar el bloque `deploy/nginx/odoo.conf` al nginx y recargarlo (`nginx -t` antes) | El sitio y `/web/login` responden |
| 7 | En Meta, cambiar el webhook a `https://<dominio>/api/v1/messaging/whatsapp/webhook`, con el mismo token de verificación | Meta acepta la verificación |
| 8 | Mensaje real de prueba desde un teléfono del equipo | Llega a Odoo, n8n responde |
| 9 | Encender los avisos automáticos en Odoo | Bandeja de salida con estados enviados |

Entre los pasos 4 y 7 (unos minutos) un mensaje real que entre por el sistema anterior
puede fallar en n8n: por eso se hace con poco tráfico y con los avisos en pausa.

## Volver atrás (cualquier momento del día o de la semana siguiente)

1. `docker compose -f docker-compose.yml up -d odoo` (sin el archivo del cambio): Odoo deja de
   llamarse `api`.
2. En el compose del sistema anterior, devolver el nombre `api` y `docker compose up -d api`.
3. En Meta, volver el webhook a la dirección anterior.
4. Quitar el bloque de nginx de Odoo y recargar.
5. Encender el beat de Celery del sistema anterior.
6. Registrar en el sistema anterior los pagos verificados en Odoo desde el cambio.

Tiempo estimado: 10 minutos. Los flujos de n8n no se tocaron, así que no hay nada que revertir
en ellos.
