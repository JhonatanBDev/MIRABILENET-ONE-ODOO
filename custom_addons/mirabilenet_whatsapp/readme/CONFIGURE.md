## Puesta en marcha

1. `MIRABILENET_MASTER_KEY` definida (ver `documentacion/claves_maestras.md`).
2. MIRABILENET > Mensajería > **Ajustes**: cuenta WABA, token, secreto de la aplicación y token
   de verificación. Nace en **modo de prueba**: arma los mensajes sin enviarlos.
3. **Números**: uno por sucursal, con su id de Meta. «Verificar» comprueba el token.
4. **Plantillas**: nombre exacto en Meta y variables en orden, por evento.
5. **QR de pago** por región, si alguna plantilla lleva imagen en el encabezado.
6. En Meta, el webhook apunta a `/api/v1/messaging/whatsapp/webhook`, la misma ruta de antes.
7. Parámetros del sistema: `mirabilenet.messaging_public_url` (dirección pública desde la que
   Meta descarga el QR) y `mirabilenet.n8n_controls_collection` (en `1`, los recordatorios los
   lleva n8n y aquí no se encolan).
