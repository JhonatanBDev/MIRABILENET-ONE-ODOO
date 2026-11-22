# Llevar el proyecto a otra computadora

Situación al 20/11/2026: dónde quedamos está en `ESTADO.md` > «Para retomar», la historia en
`documentacion/historial_mirabilenet.md` y la estructura de los módulos en
`documentacion/estandar_modulos.md`. Esos tres archivos viajan con el proyecto.

## 1. Qué hay en esta computadora

| Qué | Dónde | Tamaño | Cómo se lleva |
|---|---|---|---|
| Odoo 19 (núcleo) | `odoo/` (clon de `github.com/odoo/odoo`, rama 19.0) | 1,1 GB | Copiar la carpeta o clonarlo de nuevo |
| Módulos propios | `odoo/custom_addons/` (14 módulos) | 28 MB | **Copiar** (no están en git) |
| Módulos OCA | `odoo/oca/` (contract, event, mis-builder, reporting-engine, server-ux, geospatial) | 53 MB | Copiar o clonar de nuevo (rama 19.0) |
| Documentación y despliegue | `odoo/documentacion/`, `odoo/deploy/`, `ESTADO.md`, `AGENTS.md`, `CLAUDE.md`, `Static/` | < 2 MB | **Copiar** |
| Grafo de graphify | `odoo/graphify-out/`, `odoo/custom_addons/graphify-out/` | 1 MB | Copiar (o regenerar con `graphify update custom_addons`) |
| Entorno de Python | `odoo/env/` | 146 MB | **No copiar**: se crea de nuevo |
| Configuración local | `odoo/odoo.conf` | — | Copiar y revisar (tiene la contraseña de PostgreSQL de esta máquina) |
| Bases de datos | PostgreSQL 18 local: `mira_nativo_test`, `mira_siat_test`, `odoo` | — | Volcado y restauración (punto 3) |
| Archivos adjuntos de cada base | `%LOCALAPPDATA%\OpenERP S.A\Odoo\filestore\<base>` | 257 / 99 / 81 MB | Copiar junto con su volcado |
| Memoria de claude-mem | `%USERPROFILE%\.claude-mem\` | 102 MB | Punto 4 |
| Memoria y conversaciones de Claude Code de este proyecto | `%USERPROFILE%\.claude\projects\C--ING-SISTEMAS-SISTEMAS-Y-PROYECTOS-odoo\` | — | Punto 4 |
| Skill de graphify e instrucciones globales | `%USERPROFILE%\.claude\skills\graphify\`, `%USERPROFILE%\.claude\CLAUDE.md` | — | Copiar |
| Claves maestras | Variables de entorno de Windows `MIRABILENET_MASTER_KEY` y `MIRA_SIAT_MASTER_KEY` | — | Punto 5 (no van en archivos) |

**Nada de lo propio está en git.** El repositorio `odoo/` apunta a `github.com/odoo/odoo`
(el de Odoo, no el nuestro), y `custom_addons/`, `documentacion/`, `deploy/` y los demás están
sin seguimiento. Recomendado antes de mudarse: un repositorio privado propio (GitHub o similar)
con `custom_addons/`, `documentacion/`, `deploy/`, `Static/`, `ESTADO.md`, `AGENTS.md`,
`CLAUDE.md` y `requirements.txt`, sin `odoo.conf` ni secretos.

## 2. Preparar la computadora nueva

1. Instalar **PostgreSQL 18** (o más nuevo: un volcado de la 18 no se restaura en una más vieja)
   y crear el usuario `admin` con permiso para crear bases:
   `createuser -U postgres -d -P admin`.
2. Instalar **Python 3.10** (la versión que usa hoy `env/`).
3. Usar **la misma ruta**, `C:\ING.SISTEMAS\SISTEMAS_Y_PROYECTOS\odoo`. Si cambia, hay que
   renombrar la carpeta de memoria de Claude Code (punto 4) y revisar `odoo.conf`.
4. Copiar la carpeta `odoo/` sin `env/` (o clonar Odoo 19.0 y los repositorios de OCA y copiar
   encima lo propio).
5. Crear el entorno e instalar dependencias:
   ```powershell
   cd C:\ING.SISTEMAS\SISTEMAS_Y_PROYECTOS\odoo
   py -3.10 -m venv env
   env\Scripts\python.exe -m pip install -r requirements.txt
   ```
   Si `pip` falla con `CERTIFICATE_VERIFY_FAILED` y la máquina tiene un antivirus que escanea
   HTTPS (Avast, por ejemplo), pasarle su certificado raíz:
   `env\Scripts\python.exe -m pip config --site set global.cert "C:\ProgramData\Avast Software\Avast\wscert.pem"`
   y repetir la instalación. No usar `--trusted-host`.
6. Revisar `odoo.conf`: contraseña de PostgreSQL de la máquina nueva y `addons_path`
   (debe incluir `oca/geospatial` y `oca/web`).
7. Instalar Claude Code, el plugin **claude-mem** y **graphify** (`pip install graphifyy`), y
   copiar `%USERPROFILE%\.claude\skills\graphify\` y `%USERPROFILE%\.claude\CLAUDE.md`.

## 3. Bases de datos

Una base de Odoo son **dos partes**: la base en PostgreSQL y su carpeta de archivos
(`filestore`). Hay que llevar las dos con el mismo nombre.

En la computadora actual, con Odoo apagado:

```powershell
$pg = "C:\Program Files\PostgreSQL\18\bin"
$dst = "D:\traslado"          # una memoria USB o carpeta compartida
New-Item -ItemType Directory -Force $dst
foreach ($db in "mira_nativo_test", "odoo") {
    & "$pg\pg_dump.exe" -U admin -h localhost -Fc -f "$dst\$db.dump" $db
    Copy-Item -Recurse "$env:LOCALAPPDATA\OpenERP S.A\Odoo\filestore\$db" "$dst\filestore_$db"
}
```

En la computadora nueva:

```powershell
$pg = "C:\Program Files\PostgreSQL\18\bin"
$src = "D:\traslado"
foreach ($db in "mira_nativo_test", "odoo") {
    & "$pg\createdb.exe" -U admin -h localhost $db
    & "$pg\pg_restore.exe" -U admin -h localhost -d $db --no-owner "$src\$db.dump"
    New-Item -ItemType Directory -Force "$env:LOCALAPPDATA\OpenERP S.A\Odoo\filestore" | Out-Null
    Copy-Item -Recurse "$src\filestore_$db" "$env:LOCALAPPDATA\OpenERP S.A\Odoo\filestore\$db"
}
```

Qué base llevar:

- **`mira_nativo_test`**: la base de prueba con todos los módulos y los datos de fibra
  (región Yapacaní, 112 NAP, 27 tramos). Conviene llevarla. Si no, se rehace sola:
  `documentacion/herramientas/crear_base_nativo.py odoo.conf`, el comando de instalación de
  `ESTADO.md` > «Cómo ejecutar» y el asistente de importación de CSV con `Static/cvs naps/`.
- **`odoo`**: tu base con las aplicaciones nativas. Llévala si tiene algo que quieras conservar.
- **`mira_siat_test`**: la base vieja de pruebas del SIAT. No hace falta.

Comprobar: levantar Odoo con el comando de `ESTADO.md` > «Para retomar» y entrar a
http://127.0.0.1:8069. Si Odoo pide la clave maestra en algún aviso, es el punto 5.

## 4. claude-mem y la memoria de Claude Code

Con Claude Code **cerrado** en las dos computadoras (así la base de claude-mem queda completa):

1. **claude-mem**: copiar la carpeta completa `%USERPROFILE%\.claude-mem\` a la misma ruta de la
   computadora nueva, después de instalar el plugin. Alternativas desde Claude Code: el skill
   `claude-mem:backup-setup` (copias locales y restaurar) o `claude-mem:cloud-sync`
   (sincronizar por la cuenta cmem.ai Pro).
2. **Memoria y conversaciones de Claude Code**: copiar
   `%USERPROFILE%\.claude\projects\C--ING-SISTEMAS-SISTEMAS-Y-PROYECTOS-odoo\`. El nombre de la
   carpeta sale de la ruta del proyecto: si en la computadora nueva la ruta es otra, renombrarla
   igual que la ruta nueva (cambiando `\`, `:` y `.` por `-`).
3. Comprobar en la computadora nueva: abrir Claude Code en la carpeta del proyecto y pedir
   «recupera con claude-mem dónde lo dejamos». Debe aparecer la nota del 20/11/2026 y la lista
   de pendientes «migracion-odoo-nativo».

## 5. Claves maestras

`MIRABILENET_MASTER_KEY` y `MIRA_SIAT_MASTER_KEY` son variables de entorno de Windows de esta
computadora. No están en ningún archivo y no deben estarlo. Los secretos guardados en las bases
(tokens de Meta, contraseñas de routers, credenciales del SIAT) están cifrados con ellas: sin
las mismas claves no se pueden leer en la computadora nueva.

- Cargarlas a mano en la computadora nueva (Configuración de Windows > Variables de entorno, o
  `setx NOMBRE "valor"`), copiándolas desde un gestor de contraseñas, nunca por chat ni correo.
- **Pendiente:** las dos claves se pegaron en un chat y hay que cambiarlas antes de guardar
  secretos reales (ver `documentacion/claves_maestras.md`). Es buen momento para hacerlo en la
  mudanza: hoy las bases solo tienen datos de prueba.

## 6. Lo que no se lleva

- `odoo/env/`: se crea de nuevo.
- La carpeta temporal de la sesión con las copias de antes de la reestructuración
  (`scratchpad/backup*`): no hace falta.
- El sistema anterior `mirabilenet-one/` es otra carpeta. Si se lleva, sus secretos (`secrets/`,
  `.env*`, `*.key`, `wireguard/`, `backups/`, `*.dump`) se mudan aparte y con cuidado, no
  mezclados con este proyecto.
