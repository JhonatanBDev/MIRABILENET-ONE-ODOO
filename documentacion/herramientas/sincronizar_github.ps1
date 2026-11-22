# Sincroniza el proyecto MIRABILENET (solo lo propio, no Odoo) con su repositorio privado de GitHub.
#
# El repositorio vive en <carpeta odoo>\.mirabilenet.git, aparte del repositorio de Odoo, y solo
# ve lo que deja pasar mirabilenet_exclude.txt: custom_addons, deploy, documentacion,
# Static\plantillas, ESTADO.md, AGENTS.md, CLAUDE.md y .claude\settings.json.
# Nunca sube claves (odoo.conf, .env.odoo) ni datos de clientes (Static\Datos, Static\cvs naps).
#
# Uso (PowerShell):
#   powershell -ExecutionPolicy Bypass -File documentacion\herramientas\sincronizar_github.ps1 estado
#   powershell -ExecutionPolicy Bypass -File documentacion\herramientas\sincronizar_github.ps1 subir "qué cambió"
#   powershell -ExecutionPolicy Bypass -File documentacion\herramientas\sincronizar_github.ps1 bajar
# Primera vez en otra PC (ver documentacion\sincronizar_con_github.md):
#   ...\sincronizar_github.ps1 instalar -Url https://github.com/USUARIO/REPO.git -Raiz C:\ING.SISTEMAS\SISTEMAS_Y_PROYECTOS\odoo

param(
    [Parameter(Position = 0)][ValidateSet("estado", "subir", "bajar", "instalar")][string]$Accion = "estado",
    [Parameter(Position = 1)][string]$Mensaje = "Avance del proyecto",
    [string]$Url,
    [string]$Raiz
)
$ErrorActionPreference = "Stop"
if (-not $Raiz) { $Raiz = (Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..\..")).Path }
$G = Join-Path $Raiz ".mirabilenet.git"
$Versiones = Join-Path $Raiz "documentacion\versiones_odoo_y_oca.txt"
$Rutas = @("custom_addons", "deploy", "documentacion", "Static/plantillas", "ESTADO.md", "AGENTS.md", "CLAUDE.md")
$ConPunto = @("deploy/.env.odoo.example", ".claude/settings.json")

function Invoke-Mgit {
    & git "--git-dir=$G" "--work-tree=$Raiz" @args
    if ($LASTEXITCODE -ne 0) { throw "git $args terminó con error $LASTEXITCODE" }
}

function Save-Versiones {
    # Odoo y OCA no se suben: se anota en qué versión está cada uno para igualarlos en la otra PC.
    $lineas = @("# Versión de Odoo y de cada repositorio OCA (lo escribe sincronizar_github.ps1 al subir).")
    $lineas += "odoo $(git -C $Raiz rev-parse HEAD) $(git -C $Raiz remote get-url origin)"
    Get-ChildItem (Join-Path $Raiz "oca") -Directory | Sort-Object Name | ForEach-Object {
        if (Test-Path (Join-Path $_.FullName ".git")) {
            $lineas += "oca/$($_.Name) $(git -C $_.FullName rev-parse HEAD) $(git -C $_.FullName remote get-url origin)"
        }
    }
    [IO.File]::WriteAllText($Versiones, ($lineas -join "`n") + "`n")
}

function Sync-Oca {
    if (-not (Test-Path $Versiones)) { return }
    foreach ($linea in Get-Content $Versiones) {
        if ($linea -match "^\s*#" -or -not $linea.Trim()) { continue }
        $nombre, $commit, $origen = $linea -split " "
        $carpeta = Join-Path $Raiz $nombre
        if ($nombre -eq "odoo") {
            $actual = git -C $Raiz rev-parse HEAD
            if ($actual -ne $commit) { Write-Warning "Odoo está en $actual y la otra PC en $commit. Revisar antes de seguir." }
            continue
        }
        if (-not (Test-Path $carpeta)) {
            Write-Host "Descargando $nombre..."
            git clone -q --branch 19.0 $origen $carpeta
        }
        git -C $carpeta fetch -q origin
        git -C $carpeta merge -q --ff-only $commit
        if ($LASTEXITCODE -ne 0) { Write-Warning "$nombre no se pudo llevar a $commit (tiene cambios propios)." }
        else { Write-Host "$nombre al día ($($commit.Substring(0,7)))" }
    }
}

switch ($Accion) {
    "estado" {
        Invoke-Mgit status --short
    }
    "subir" {
        Save-Versiones
        Invoke-Mgit add -A -- @Rutas
        Invoke-Mgit add -f -- @ConPunto
        & git "--git-dir=$G" "--work-tree=$Raiz" diff --cached --quiet
        if ($LASTEXITCODE -ne 0) { Invoke-Mgit commit -q -m $Mensaje } else { Write-Host "No hay cambios nuevos." }
        Invoke-Mgit push -u origin main
        Write-Host "Subido. En la otra PC: sincronizar_github.ps1 bajar"
    }
    "bajar" {
        Invoke-Mgit pull --ff-only origin main
        Sync-Oca
        Write-Host "Listo. Si cambió algún módulo, actualizarlo en Odoo (-u modulo) o desde Aplicaciones."
    }
    "instalar" {
        if (-not $Url) { throw "Falta -Url con la dirección del repositorio de GitHub." }
        if (Test-Path $G) { throw "Ya existe $G; use 'bajar'." }
        # Respaldo de lo que hay hoy en esta PC antes de reemplazarlo con lo de GitHub.
        $fecha = Get-Date -Format "yyyy-MM-dd_HHmm"
        $respaldo = Join-Path (Split-Path $Raiz) "respaldo_antes_github_$fecha.zip"
        $existentes = $Rutas | ForEach-Object { Join-Path $Raiz $_ } | Where-Object { Test-Path $_ }
        if ($existentes) { Compress-Archive -Path $existentes -DestinationPath $respaldo; Write-Host "Respaldo: $respaldo" }
        git clone -q --bare $Url $G
        if ($LASTEXITCODE -ne 0) { throw "No se pudo descargar $Url" }
        git "--git-dir=$G" config core.bare false
        git "--git-dir=$G" config core.worktree $Raiz
        git "--git-dir=$G" config core.autocrlf false
        git "--git-dir=$G" config status.showUntrackedFiles no
        git "--git-dir=$G" config user.name JhonatanBDev
        git "--git-dir=$G" config remote.origin.fetch "+refs/heads/*:refs/remotes/origin/*"
        Invoke-Mgit reset -q --hard main
        Copy-Item (Join-Path $Raiz "documentacion\herramientas\mirabilenet_exclude.txt") (Join-Path $G "info\exclude") -Force
        Invoke-Mgit fetch -q origin
        Invoke-Mgit branch -q --set-upstream-to=origin/main main
        Sync-Oca
        Write-Host "Instalado. Configure el correo del autor: git --git-dir=`"$G`" config user.email SU_CORREO"
    }
}
