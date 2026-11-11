<#
.SYNOPSIS
    Startet alle drei Halle-Gehirn-Dienste mit den RICHTIGEN Ports.

.DESCRIPTION
    Port-Zuordnung (kanonisch):
      3000  Chat-Frontend     (Preact-Widget, Vite dev-server)
      3001  Wissensbestand    (Preact, Vite dev-server)
      8001  API               (FastAPI / uvicorn)

    Jeder Dienst laeuft in einem eigenen PowerShell-Job.
    Ctrl+C beendet alle drei.

.NOTES
    Voraussetzungen:
      - Python venv aktiviert ODER uv verfuegbar
      - Node + npm im PATH (Node LTS empfohlen; Vite 6 unterstuetzt ^18/^20/^22)
      - Node-Abhaengigkeiten werden bei Bedarf automatisch installiert:
          cd frontend/jarvis-widget && npm install
          cd frontend/jarvis-wissensbestand && npm install
      - Qdrant + Ollama extern gestartet
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -- Projekt-Root (dort, wo dieses Skript liegt: scripts/) --
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

# -- Ports (kanonisch, siehe CLAUDE.md) --
$API_PORT      = 8001
$CHAT_PORT     = 3000
$WISSEN_PORT   = 3001

# -- Python: venv bevorzugen, Fallback auf System-Python --
$venvPython = Join-Path $root ".venv/Scripts/python.exe"
if (-not (Test-Path $venvPython)) {
    $venvPython = "python"
    Write-Host "  WARNUNG: Kein .venv gefunden, nutze System-Python" -ForegroundColor Yellow
}

# -- Alte Prozesse auf den Ports beenden (verhindert Port-Konflikte) --
function Stop-PortProcess($port) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        $procIds = $conn | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($procId in $procIds) {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Host "  Port $port belegt von PID $procId ($($proc.ProcessName)) - beende..." -ForegroundColor Yellow
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            }
        }
        Start-Sleep -Milliseconds 500
    }
}

Write-Host ""
Write-Host "=== Halle-Gehirn - Alle Dienste starten ===" -ForegroundColor Cyan
Write-Host ""

# Alte Prozesse raeumen
Write-Host "Pruefe Ports..." -ForegroundColor Gray
Stop-PortProcess $API_PORT
Stop-PortProcess $CHAT_PORT
Stop-PortProcess $WISSEN_PORT

# -- Node-Dependencies pruefen: lokales Vite MUSS vorhanden sein --
# Fehlt node_modules, faellt npx auf seinen globalen Download-Cache
# (%LOCALAPPDATA%\npm-cache\_npx) zurueck, der defekt sein kann
# -> ERR_MODULE_NOT_FOUND. Siehe plans/fix-wissensbestand-vite-startup.md
function Ensure-NodeDeps($relDir) {
    $dir = Join-Path $root $relDir
    if (-not (Test-Path (Join-Path $dir "node_modules\vite"))) {
        Write-Host "  Installiere npm-Abhaengigkeiten in $relDir ..." -ForegroundColor Yellow
        Push-Location $dir
        npm install
        $code = $LASTEXITCODE
        Pop-Location
        if ($code -ne 0) {
            throw "npm install in $relDir fehlgeschlagen (Exit $code). Bitte manuell ausfuehren und erneut starten."
        }
    }
}
Ensure-NodeDeps "frontend/jarvis-widget"
Ensure-NodeDeps "frontend/jarvis-wissensbestand"

Write-Host ""
Write-Host "  API              http://localhost:$API_PORT"
Write-Host "  Chat-Frontend    http://localhost:$CHAT_PORT"
Write-Host "  Wissensbestand   http://localhost:$WISSEN_PORT"
Write-Host ""

# -- 1. API (FastAPI / uvicorn) --
$apiJob = Start-Job -Name "API" -ScriptBlock {
    param($r, $p, $py)
    Set-Location $r
    & $py -m uvicorn halle_gehirn.api.main:app `
        --host 0.0.0.0 --port $p --reload 2>&1
} -ArgumentList $root, $API_PORT, $venvPython

# -- 2. Chat-Frontend (Preact / Vite) --
$chatJob = Start-Job -Name "Chat" -ScriptBlock {
    param($r, $p)
    Set-Location "$r/frontend/jarvis-widget"
    & npm run dev -- --port $p --strictPort --host 2>&1
} -ArgumentList $root, $CHAT_PORT

# -- 3. Wissensbestand (Preact / Vite) --
$wissenJob = Start-Job -Name "Wissensbestand" -ScriptBlock {
    param($r, $p)
    Set-Location "$r/frontend/jarvis-wissensbestand"
    & npm run dev -- --port $p --strictPort --host 2>&1
} -ArgumentList $root, $WISSEN_PORT

Write-Host "Dienste gestartet. Druecke Ctrl+C zum Beenden aller Dienste." -ForegroundColor Green
Write-Host ""

# -- Log-Streaming: gibt Output aller drei Jobs aus --
try {
    while ($true) {
        $apiJob, $chatJob, $wissenJob | ForEach-Object {
            $name = $_.Name
            Receive-Job -Job $_ 2>&1 | ForEach-Object {
                Write-Host "[$name] $_"
            }
        }
        Start-Sleep -Milliseconds 500
    }
} finally {
    Write-Host ""
    Write-Host "Beende alle Dienste..." -ForegroundColor Yellow
    $apiJob, $chatJob, $wissenJob | ForEach-Object {
        Stop-Job -Job $_ -ErrorAction SilentlyContinue
        Remove-Job -Job $_ -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Alle Dienste beendet." -ForegroundColor Green
}
