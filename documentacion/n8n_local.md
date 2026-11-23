# n8n en esta PC, conectado a Odoo

Es el n8n del sistema anterior (MIRABILENET ONE), traído el 23/11/2026 con sus 10 flujos y sus 5
credenciales, y apuntado a Odoo en vez de a la API de Django.

## Dónde está

- `C:\ING.SISTEMAS\n8n_local\docker-compose.yml` levanta n8n 2.43.7 en
  **http://127.0.0.1:5679**, con el mismo usuario y contraseña de la otra PC.
- **Los datos** (flujos, credenciales y su clave de cifrado) están en el volumen de Docker
  `n8n_local`.
- `C:\ING.SISTEMAS\n8n_local\flujos_odoo\` tiene los 10 flujos que se importaron, con
  `http://api:8000` cambiado por `http://host.docker.internal:8069`.
- `C:\ING.SISTEMAS\n8n_local\traslado\` tiene lo que llegó de la otra PC: el volumen original, los
  tokens y los flujos sin cambios. **Tiene secretos:** no va a GitHub ni a la nube.

Nada de esto está dentro del proyecto `odoo\`.

## Cómo se conectan

- **n8n → Odoo:** los flujos llaman a `http://host.docker.internal:8069/api/v1/messaging/n8n/...`
  (`mirabilenet_whatsapp/controllers/n8n_api.py`). Presentan el token de la credencial
  «MIRABILENET API», que Odoo compara con `MIRABILENET_N8N_API_TOKEN`.
- **Odoo → n8n:** Odoo firma cada evento con `MIRABILENET_N8N_WEBHOOK_SECRET` (cabecera y JWT de
  2 minutos con el hash del cuerpo).
  - Lo manda al parámetro `mirabilenet.n8n_inbound_webhook_url`, que es
    `http://127.0.0.1:5679/webhook/mirabilenet-entrante`.
  - El flujo «10 Entrada de mensajes» verifica la firma.
- **Los dos tokens** son variables de entorno del usuario de Windows: los mismos valores que la
  otra PC tenía como `N8N_API_TOKEN` y `N8N_WEBHOOK_SECRET`. No van en `odoo.conf` ni en Git.
- **Odoo entrega los eventos con un cron**, así que hay que arrancarlo con `--max-cron-threads 1` o
  más.

## Flujo «20 Personal» (técnicos y personal)

Lo que el personal escribe con sus palabras, por ejemplo «ya quedó, era el conector», le
llega a n8n en `/webhook/mirabilenet-personal`, firmado igual que los mensajes de clientes.
- Gemini lo interpreta y n8n le contesta a Odoo en
  `/api/v1/messaging/n8n/personal/resultado`.
- En Odoo, el parámetro `mirabilenet.n8n_staff_webhook_url` vale
  `http://127.0.0.1:5679/webhook/mirabilenet-personal`.
- El flujo se arma con `documentacion/herramientas/generar_flujo_20_personal.py`, a partir
  de los flujos 10 y 15, así usa las mismas credenciales. El resultado está en
  `documentacion/n8n/20_personal.json`.
- Probado de punta a punta el 23/11/2026: el técnico escribió con sus palabras, Gemini lo
  entendió como «arreglado» y Odoo cerró la avería con la nota.

## Arrancar

1. Abrir Docker Desktop. n8n arranca solo (`restart: unless-stopped`). Si no:
   ```
   cd C:\ING.SISTEMAS\n8n_local
   docker compose up -d
   ```
2. Odoo, en Git Bash, desde la carpeta `odoo`:
   ```
   for k in MIRABILENET_MASTER_KEY MIRA_SIAT_MASTER_KEY MIRABILENET_N8N_API_TOKEN MIRABILENET_N8N_WEBHOOK_SECRET; do
     export $k="$(powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('$k','User')")"; done
   env/Scripts/python.exe odoo-bin -c odoo.conf -d mira_nativo_test --db-filter "^mira_nativo_test$" --http-port 8069 --max-cron-threads 1
   ```

## Probar

- En n8n, abrir «MIRABILENET · 00 Prueba de conexión con la API» y ejecutarlo. Responde Odoo; un
  403 quiere decir que el token no coincide.
- Por consola, con n8n corriendo:
  ```
  docker exec -e N8N_RUNNERS_BROKER_PORT=5690 n8n_local n8n execute --id JnHnWembAhzVI8cN
  ```

## Volver a importar los flujos (si se cambian en otra parte)

Con n8n detenido (`docker compose stop`), importar con `n8n import:workflow --separate` desde un
contenedor temporal con el volumen montado. Antes, cambiar la dirección de la API en los JSON.
Después, reactivar los flujos con `n8n update:workflow --id=… --active=true`, porque la importación
los deja apagados.

## Volver atrás

```
cd C:\ING.SISTEMAS\n8n_local
docker compose down
docker volume rm n8n_local
```
Para restaurar el original, hay que volver a cargar `traslado\...\n8n_local.tar.gz` en un volumen
nuevo. En Odoo, quitar el parámetro `mirabilenet.n8n_inbound_webhook_url` y las dos variables de
entorno.

## Para producción (VPS)

En el VPS, n8n ya corre junto al sistema actual. Al pasar a Odoo:
- los flujos deben llamar a Odoo por la red interna de Docker (`http://odoo:8069`);
- el parámetro del webhook debe apuntar a `http://n8n:5678/webhook/mirabilenet-entrante`;
- los dos tokens van en `.env.odoo` (ver `deploy/.env.odoo.example`).
