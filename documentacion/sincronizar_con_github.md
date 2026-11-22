# Sincronizar el proyecto entre computadoras con GitHub

El proyecto propio de MIRABILENET va en un repositorio **privado** de GitHub, aparte del
repositorio de Odoo. Vive en `odoo\.mirabilenet.git` y solo ve:

- `custom_addons\` (sin `graphify-out`), `deploy\`, `documentacion\`, `Static\plantillas\`;
- `ESTADO.md`, `AGENTS.md`, `CLAUDE.md` y `.claude\settings.json`;
- `documentacion\versiones_odoo_y_oca.txt`: en qué versión está Odoo y cada repositorio OCA.

**Nunca van a GitHub:**

- `odoo.conf` y `.env.odoo`;
- las claves maestras;
- `Static\Datos\` y `Static\cvs naps\` (datos reales de clientes);
- las bases de datos y su filestore;
- el entorno `env\`;
- la memoria de Claude.

Eso se lleva por USB o Drive (ver `trasladar_a_otra_pc.md`). La lista de lo que entra está en
`herramientas\mirabilenet_exclude.txt`.

## Uso diario

En PowerShell, dentro de la carpeta `odoo`:

```
$s = "documentacion\herramientas\sincronizar_github.ps1"
powershell -ExecutionPolicy Bypass -File $s estado               # qué cambió
powershell -ExecutionPolicy Bypass -File $s subir "qué hice"     # al terminar en una PC
powershell -ExecutionPolicy Bypass -File $s bajar                # al empezar en la otra
```

`bajar` también lleva los repositorios OCA a la misma versión, y avisa si Odoo está en otra.
Después de bajar, actualice en Odoo los módulos que cambiaron (`-u modulo`).

Regla: **subir siempre antes de cambiar de PC**. Si las dos PC cambian lo mismo sin sincronizar,
`bajar` se detiene. En ese caso, pedir ayuda antes de forzar nada.

## Primera vez en otra PC (ya con la carpeta `odoo` de Odoo 19)

```
git clone https://github.com/USUARIO/REPO.git C:\ING.SISTEMAS\mirabilenet_tmp
powershell -ExecutionPolicy Bypass -File C:\ING.SISTEMAS\mirabilenet_tmp\documentacion\herramientas\sincronizar_github.ps1 instalar -Url https://github.com/USUARIO/REPO.git -Raiz C:\ING.SISTEMAS\SISTEMAS_Y_PROYECTOS\odoo
Remove-Item -Recurse -Force C:\ING.SISTEMAS\mirabilenet_tmp
```

`instalar` hace tres cosas:

1. Respalda en un ZIP lo que esa PC tenía (`SISTEMAS_Y_PROYECTOS\respaldo_antes_github_<fecha>.zip`).
2. Reemplaza los archivos por los de GitHub.
3. Iguala los repositorios OCA.

Los archivos que en esa PC existían y aquí se borraron quedan sueltos: revisarlos con `estado`.

Después:

- cargar la base (`.dump` y filestore) que vino por USB;
- poner las **mismas claves maestras de la PC donde se cifraron los datos**;
- actualizar los módulos: `-u all` o la lista de `ESTADO.md`.
