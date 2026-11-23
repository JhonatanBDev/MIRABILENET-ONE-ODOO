# Flujos de n8n

- `docker-compose.yml`: el n8n local (queda en http://localhost:5679).
- `flujos\`: todos los flujos, con su número y su identificador. No traen credenciales: solo el
  nombre y el identificador de la credencial que usan. En otra PC hay que crear las credenciales
  y volver a elegirlas en los nodos (ver `..\INSTALAR_EN_OTRA_PC.md`, paso 9).
- `15_soporte.json`, `17_ventas.json` y `20_personal.json`: copia de los tres flujos que
  generan los guiones de `..\herramientas\`.

| Flujo | Qué hace |
|---|---|
| 00 | Prueba de conexión con la API de Odoo |
| 10 | Entrada de mensajes: verifica la firma y reparte |
| 11 | Enviar mensaje |
| 12 | Eco de prueba |
| 13 y 14 | Comprobantes de pago |
| 15 | Soporte: agente con IA para clientes (incluye cotizaciones) |
| 16 | Derivar a una persona |
| 17 | Ventas: agente para interesados (incluye cotizaciones) |
| 19 | Alertas de errores |
| 20 | Personal: respuestas de técnicos y «cotiza…» |
