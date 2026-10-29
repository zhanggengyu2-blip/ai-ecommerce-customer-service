$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
Push-Location (Join-Path $projectRoot 'backend')
try {
    & $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
} finally {
    Pop-Location
}
