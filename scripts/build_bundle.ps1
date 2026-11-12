<#
.SYNOPSIS
    Baut das Halle-Gehirn Standalone-Bundle (portabler Ordner + ZIP).

.DESCRIPTION
    Ergebnis: dist/halle-gehirn-app/ mit halle-gehirn.exe (PyInstaller onedir),
    statischen Frontends (chat + admin), data/, caches/ (tiktoken + fastembed
    offline vorgewaermt), .env und README. Kein Python/Node auf dem Ziel-PC.

    Externe Dienste auf dem Ziel-PC erforderlich: Qdrant, Ollama
    (LLM+Embeddings), Docling Serve — konfiguriert in der .env des Bundles.

.NOTES
    Voraussetzungen (Build-PC): uv/venv mit dev-Extras, Node + npm.
    Aufruf:  powershell -File scripts/build_bundle.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$py = Join-Path $root ".venv/Scripts/python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$out = Join-Path $root "dist/halle-gehirn-app"
Write-Host "=== Halle-Gehirn Bundle-Build ===" -ForegroundColor Cyan
Write-Host "Ziel: $out" -ForegroundColor Gray

# -- 1. Frontend-Builds --
foreach ($app in "jarvis-widget", "jarvis-wissensbestand") {
    $dir = Join-Path $root "frontend/$app"
    if (-not (Test-Path (Join-Path $dir "node_modules/vite"))) {
        Write-Host "  npm install in frontend/$app ..." -ForegroundColor Yellow
        Push-Location $dir; npm install; Pop-Location
        if ($LASTEXITCODE -ne 0) { throw "npm install in $app fehlgeschlagen" }
    }
    Push-Location $dir; npm run build; Pop-Location
    if ($LASTEXITCODE -ne 0) { throw "vite build in $app fehlgeschlagen" }
}

# -- 2. PyInstaller (onedir) --
Write-Host "  PyInstaller ..." -ForegroundColor Yellow
Push-Location (Join-Path $root "bundle")
& $py -m PyInstaller --noconfirm --clean pyinstaller.spec
Pop-Location
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fehlgeschlagen" }

# -- 3. Bundle-Ordner zusammenstellen --
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force -Path $out | Out-Null

# 3a. PyInstaller-Output auf Bundle-Root kopieren (exe + _internal/)
Copy-Item -Recurse (Join-Path $root "bundle/dist/halle-gehirn/*") $out

# 3b. Statische Frontends
New-Item -ItemType Directory -Force -Path "$out/static/chat", "$out/static/admin" | Out-Null
Copy-Item -Recurse (Join-Path $root "frontend/jarvis-widget/dist/*") "$out/static/chat"
Copy-Item -Recurse (Join-Path $root "frontend/jarvis-wissensbestand/dist/*") "$out/static/admin"

# 3c. Daten (Kuration + Vokabular + Figuren)
Copy-Item -Recurse (Join-Path $root "data") "$out/data"
New-Item -ItemType Directory -Force -Path "$out/logs/retrieval" | Out-Null

# 3d. Offline-Caches vorwaermen (tiktoken cl100k_base, FastEmbed BM25)
New-Item -ItemType Directory -Force -Path "$out/caches/tiktoken", "$out/caches/fastembed" | Out-Null
Write-Host "  Waerme tiktoken-Cache vor ..." -ForegroundColor Yellow
$env:TIKTOKEN_CACHE_DIR = "$out/caches/tiktoken"
& $py scripts/cache_tiktoken.py 2>&1 | Out-Null
# cache_tiktoken schreibt in .tiktoken_cache — Dateien uebernehmen
$devCache = Join-Path $root ".tiktoken_cache"
if (Test-Path $devCache) { Copy-Item "$devCache/*" "$out/caches/tiktoken" -Force }
Write-Host "  Waerme FastEmbed-Cache vor (BM25, deutsch) ..." -ForegroundColor Yellow
$env:FASTEMBED_CACHE_PATH = "$out/caches/fastembed"
& $py -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding('Qdrant/bm25', language='german'); print('fastembed cache ok')"

# 3e. Konfiguration + Start + Doku
Copy-Item (Join-Path $root "bundle/env.template") "$out/.env"
Copy-Item (Join-Path $root "bundle/start.cmd") "$out/start.cmd"
Copy-Item (Join-Path $root "bundle/README.template") "$out/README.md"
Copy-Item (Join-Path $root "bundle/env.template") "$out/env.beispiel"

# -- 4. ZIP --
$zip = Join-Path $root "dist/halle-gehirn-app.zip"
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path $out -DestinationPath $zip

$sizeMB = [math]::Round((Get-ChildItem $out -Recurse | Measure-Object Length -Sum).Sum / 1MB)
Write-Host ""
Write-Host "Fertig: $out (${sizeMB} MB)" -ForegroundColor Green
Write-Host "ZIP:    $zip" -ForegroundColor Green
Write-Host "Verteilen: ZIP entpacken, .env pruefen, start.cmd ausfuehren."
