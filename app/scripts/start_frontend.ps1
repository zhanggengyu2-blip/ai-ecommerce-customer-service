$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $projectRoot 'frontend')
try {
    npm.cmd run dev -- --host 127.0.0.1
} finally {
    Pop-Location
}
