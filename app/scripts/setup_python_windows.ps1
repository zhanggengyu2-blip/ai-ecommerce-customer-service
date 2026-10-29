$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$requirements = Join-Path $projectRoot 'backend\requirements.txt'
$venvPath = Join-Path $projectRoot '.venv'
$pythonPath = Join-Path $venvPath 'Scripts\python.exe'
$indexUrl = $env:PIP_INDEX_URL
if ([string]::IsNullOrWhiteSpace($indexUrl)) { $indexUrl = 'https://pypi.tuna.tsinghua.edu.cn/simple' }

if (-not (Test-Path -LiteralPath $requirements)) {
    throw "Requirements file not found: $requirements"
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv $venvPath
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $venvPath
    } else {
        throw 'Python 3 was not found. Install Python 3 and ensure py.exe or python.exe is on PATH.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python virtual environment.' }
}

& $pythonPath -m pip install -r $requirements --index-url $indexUrl
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }

Write-Output "Python environment ready: $venvPath"
