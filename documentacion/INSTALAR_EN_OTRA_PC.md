# Instalar y hacer correr el sistema en otra computadora (Windows)

Este repositorio trae **solo lo propio** del proyecto: los módulos de `custom_addons\`, la
documentación, los guiones y los flujos de n8n. Odoo 19 y los módulos de la comunidad (OCA) se
bajan aparte, en la versión exacta que anota `documentacion\versiones_odoo_y_oca.txt`.

Lo que **no** está aquí, a propósito: contraseñas, claves maestras, datos de clientes, bases
de datos y márgenes de ganancia. Cómo conseguir cada cosa está en el paso 6 y en
`PENDIENTES_DE_CONFIGURACION.md`.

## 1. Programas

| Programa | Versión | Nota |
|---|---|---|
| Git | cualquiera reciente | Incluye Git Bash |
| Python | 3.10 | Marcar «Add to PATH» |
| PostgreSQL | 16 o superior | Crear un usuario para Odoo (aquí se llama `admin`) |
| wkhtmltopdf | 0.12.6 (con Qt parchado) | Para los PDF; queda en `C:\Program Files\wkhtmltopdf\bin` |
| Docker Desktop | cualquiera reciente | Solo si se va a usar n8n |

## 2. Odoo 19

```
mkdir C:\ING.SISTEMAS\SISTEMAS_Y_PROYECTOS
cd C:\ING.SISTEMAS\SISTEMAS_Y_PROYECTOS
git clone --branch 19.0 https://github.com/odoo/odoo.git odoo
cd odoo
git checkout dc1f2561cda785530d55b85de70a4b44243f5200
```

Ese es el commit de Odoo con el que se probó todo. Si `versiones_odoo_y_oca.txt` dice otro,
vale el del archivo.

## 3. El proyecto y los módulos de la comunidad

```
git clone https://github.com/JhonatanBDev/MIRABILENET-ONE-ODOO.git C:\ING.SISTEMAS\mirabilenet_tmp
powershell -ExecutionPolicy Bypass -File C:\ING.SISTEMAS\mirabilenet_tmp\documentacion\herramientas\sincronizar_github.ps1 instalar -Url https://github.com/JhonatanBDev/MIRABILENET-ONE-ODOO.git -Raiz C:\ING.SISTEMAS\SISTEMAS_Y_PROYECTOS\odoo
Remove-Item -Recurse -Force C:\ING.SISTEMAS\mirabilenet_tmp
```

`instalar` copia el proyecto dentro de la carpeta `odoo`, clona en `odoo\oca\` los siete
repositorios de la comunidad y los deja en su versión. Detalle y uso diario (`subir`, `bajar`,
`estado`) en `sincronizar_con_github.md`.

## 4. Entorno de Python

En la carpeta `odoo`:

```
py -3.10 -m venv env
env\Scripts\python.exe -m pip install --upgrade pip
env\Scripts\python.exe -m pip install -r requirements.txt
env\Scripts\python.exe -m pip install -r documentacion\requisitos_extra.txt
```

- Si `libsass==0.20.1` no instala, cambie esa línea de `requirements.txt` por
  `libsass>=0.20.1`.
- Si el antivirus intercepta las conexiones seguras y `pip` falla por el certificado, cree
  `env\pip.ini` con `[global]` y `trusted-host = pypi.org files.pythonhosted.org`.

## 5. Configuración de Odoo

```
copy documentacion\odoo.conf.ejemplo odoo.conf
```

Edite `odoo.conf` y ponga la contraseña del usuario de PostgreSQL y una contraseña maestra de
Odoo. Ese archivo no se sube a GitHub.

## 6. Claves y variables de entorno

Son variables de entorno **del usuario de Windows** (Configuración > Variables de entorno).
Nunca van en archivos ni en GitHub.

| Variable | Para qué | De dónde sale |
|---|---|---|
| `MIRABILENET_MASTER_KEY` | Cifra contraseñas de routers, PPPoE, WhatsApp y DigiCorp | Base nueva: invente una larga y guárdela. Base traída de otra PC: **la misma de esa PC** |
| `MIRA_SIAT_MASTER_KEY` | Cifra las credenciales de facturación | Igual que la anterior |
| `MIRABILENET_N8N_API_TOKEN` | Ficha con la que n8n entra a la API | La misma que tiene la credencial «MIRABILENET API» en n8n |
| `MIRABILENET_N8N_WEBHOOK_SECRET` | Firma de los eventos hacia n8n | La misma que tiene la credencial «MIRABILENET Webhook (JWT)» |

Más detalle en `claves_maestras.md`. Si se pierde una clave maestra, lo cifrado con ella no se
recupera.

## 7. Base de datos

**Opción A, base nueva y vacía** (para probar el programa):

```
createdb -U admin -h localhost -T template1 mira_nativo_test
env\Scripts\python.exe odoo-bin -c odoo.conf -d mira_nativo_test -i mira_sale_siat,mirabilenet_base,mirabilenet_isp,mirabilenet_contratos,mirabilenet_contratos_siat,mirabilenet_inventario,mirabilenet_whatsapp,mirabilenet_web,mirabilenet_aerolab,mirabilenet_pasantias,mirabilenet_pos,mirabilenet_indicadores,mirabilenet_fibra,mirabilenet_cartera,mirabilenet_tema,mirabilenet_modo_oscuro,mirabilenet_dashboard,mirabilenet_personal,mirabilenet_cotizador,mirabilenet_cotizador_whatsapp,hr_attendance --without-demo=all --stop-after-init
```

**Opción B, con los datos de la otra PC:** restaure el `.dump` y el filestore que están en el
repositorio privado de datos, como indica `trasladar_a_otra_pc.md`, y después actualice los
módulos:

```
env\Scripts\python.exe odoo-bin -c odoo.conf -d mira_nativo_test -u all --stop-after-init
```

## 8. Arrancar

En Git Bash, desde la carpeta `odoo`:

```
for k in MIRABILENET_MASTER_KEY MIRA_SIAT_MASTER_KEY MIRABILENET_N8N_API_TOKEN MIRABILENET_N8N_WEBHOOK_SECRET; do
  export $k="$(powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('$k','User')")"; done
env/Scripts/python.exe odoo-bin -c odoo.conf -d mira_nativo_test --db-filter "^mira_nativo_test$" --http-port 8069 --max-cron-threads 1
```

Abra http://localhost:8069. El menú del sistema es «MIRABILENET». Hace falta
`--max-cron-threads 1` o más: las tareas programadas envían los mensajes y los eventos a n8n.

## 9. n8n (opcional: bot y personal por WhatsApp)

```
mkdir C:\ING.SISTEMAS\n8n_local
copy documentacion\n8n\docker-compose.yml C:\ING.SISTEMAS\n8n_local\
cd C:\ING.SISTEMAS\n8n_local
docker compose up -d
```

n8n queda en http://localhost:5679. Después:

1. Cree en n8n las tres credenciales con **estos nombres**: «MIRABILENET API» (cabecera
   `Authorization` con la ficha del paso 6), «MIRABILENET Webhook (JWT)» (el secreto del
   paso 6) y «Google Gemini(PaLM) Api account» (su clave de Gemini).
2. Importe los flujos de `documentacion\n8n\flujos\` y vuelva a elegir la credencial en los
   nodos que la piden: los flujos guardan el identificador de la credencial de la PC donde se
   hicieron.
3. Active los flujos y ejecute «00 Prueba de conexión con la API».

Si en cambio trae el volumen de n8n de la otra PC (está en el repositorio privado de datos),
las credenciales y los flujos ya vienen puestos. Detalle en `n8n_local.md`.

## 10. Comprobar

```
env\Scripts\python.exe odoo-bin -c odoo.conf -d mira_pruebas_tmp -i mirabilenet_cotizador_whatsapp,mirabilenet_pasantias --without-demo=all --test-tags mirabilenet_cotizador_whatsapp,mirabilenet_personal,mirabilenet_cotizador,mirabilenet_pasantias --stop-after-init --http-port 8079
```

Debe terminar con «0 failed, 0 error(s)». Cree antes la base con
`createdb -T template1 mira_pruebas_tmp` y bórrela después.

## Qué falta configurar

El programa corre con lo anterior, pero varias funciones necesitan datos o cuentas reales
(WhatsApp de Meta, DigiCorp, facturación, moneda de la empresa…). La lista completa está en
`PENDIENTES_DE_CONFIGURACION.md`.
