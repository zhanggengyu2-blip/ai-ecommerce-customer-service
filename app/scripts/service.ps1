param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('backend', 'frontend', 'opensearch')]
    [string]$Service,
    [Parameter(Mandatory = $true, Position = 1)]
    [ValidateSet('start', 'stop', 'status')]
    [string]$Action
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $root 'var\run'
$logDir = Join-Path $root 'var\log'
$pidFile = Join-Path $runtimeDir "$Service.json"
$stdoutLog = Join-Path $logDir "$Service.stdout.log"
$stderrLog = Join-Path $logDir "$Service.stderr.log"
$ports = @{ backend = 8001; frontend = 6173; opensearch = 9200 }
$port = $ports[$Service]
$backendPath = Join-Path $root 'backend'
$frontendPath = Join-Path $root 'frontend'
$pythonPath = Join-Path $root '.venv\Scripts\python.exe'
$openSearchHome = if ($env:OPENSEARCH_HOME) { $env:OPENSEARCH_HOME } else { 'D:\soft\opensearch-3.8.0' }

New-Item -ItemType Directory -Path $runtimeDir, $logDir -Force | Out-Null

function Test-Port([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $client.Connect('127.0.0.1', $Port)
        return $true
    } catch [System.Net.Sockets.SocketException] {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Assert-OpenSearchInstall {
    $launcher = Join-Path $openSearchHome 'bin\opensearch.bat'
    if (-not (Test-Path -LiteralPath $openSearchHome -PathType Container)) {
        throw "OpenSearch installation not found: $openSearchHome. Install OpenSearch 3.8.0 there or set OPENSEARCH_HOME to its installation directory."
    }
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw "OpenSearch launcher not found: $launcher"
    }
}

function Get-TrackedProcess {
    if (-not (Test-Path -LiteralPath $pidFile -PathType Leaf)) { return $null }
    $record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$record.pid)" -ErrorAction SilentlyContinue
    if (-not $process) {
        Remove-Item -LiteralPath $pidFile -Force
        return $null
    }

    $command = [string]$process.CommandLine
    $matchesService = switch ($Service) {
        backend { $command -match 'uvicorn' -and $command -match 'app\.main:app' }
        frontend { $command -match 'npm(\.cmd)?\s+run\s+dev' -and $command -match '6173' }
        opensearch { $command -match [regex]::Escape($openSearchHome) -and $command -match 'opensearch\.bat' }
    }
    if (-not $matchesService -or $record.root -ne $root) {
        throw "Recorded PID $($record.pid) no longer matches the $Service process; refusing to signal it."
    }
    return $process
}

function Start-TrackedProcess([string]$Executable, [string[]]$Arguments, [string]$WorkingDirectory) {
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru
    $record = @{
        service = $Service
        pid = $process.Id
        root = $root
        startedUtc = $process.StartTime.ToUniversalTime().ToString('o')
    } | ConvertTo-Json
    [System.IO.File]::WriteAllText($pidFile, $record, [System.Text.UTF8Encoding]::new($false))
    return $process
}

if ($Service -eq 'opensearch') { Assert-OpenSearchInstall }

switch ($Action) {
    status {
        $process = Get-TrackedProcess
        if ($process) {
            Write-Output "$Service RUNNING (pid $($process.ProcessId), port $port)"
            exit 0
        }
        if (Test-Port $port) {
            throw "$Service is not managed by this script, but port $port is occupied."
        }
        Write-Output "$Service STOPPED"
    }
    start {
        $process = Get-TrackedProcess
        if ($process) {
            Write-Output "$Service is already running (pid $($process.ProcessId))."
            exit 0
        }
        if (Test-Port $port) { throw "Port $port is already occupied; refusing to start $Service." }
        if ($Service -eq 'opensearch' -and (Test-Port 9300)) { throw 'Port 9300 is already occupied; refusing to start OpenSearch.' }

        switch ($Service) {
            backend {
                if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
                    throw "Python environment not found: $pythonPath. Run the Python setup script first."
                }
                $null = Start-TrackedProcess -Executable $pythonPath -Arguments @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8001') -WorkingDirectory $backendPath
            }
            frontend {
                if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'npm.cmd was not found on PATH.' }
                $null = Start-TrackedProcess -Executable $env:ComSpec -Arguments @('/d', '/c', 'npm.cmd run dev -- --host 127.0.0.1 --port 6173 --strictPort') -WorkingDirectory $frontendPath
            }
            opensearch {
                $oldJavaHome = $env:OPENSEARCH_JAVA_HOME
                $bundledJava = Join-Path $openSearchHome 'jdk'
                if (Test-Path -LiteralPath (Join-Path $bundledJava 'bin\java.exe')) { $env:OPENSEARCH_JAVA_HOME = $bundledJava }
                $batch = Join-Path $openSearchHome 'bin\opensearch.bat'
                $arguments = '/d /c call "' + $batch + '" -Ecluster.name=agentserve-local -Enode.name=agentserve-windows -Enetwork.host=127.0.0.1 -Ehttp.port=9200 -Etransport.port=9300 -Ediscovery.type=single-node -Eplugins.security.disabled=true'
                try {
                    $null = Start-TrackedProcess -Executable $env:ComSpec -Arguments @($arguments) -WorkingDirectory $openSearchHome
                } finally {
                    $env:OPENSEARCH_JAVA_HOME = $oldJavaHome
                }
            }
        }

        $timeout = if ($Service -eq 'opensearch') { 180 } else { 45 }
        for ($attempt = 0; $attempt -lt $timeout; $attempt++) {
            if (Test-Port $port) {
                $process = Get-TrackedProcess
                Write-Output "$Service started (pid $($process.ProcessId), port $port); logs: $stdoutLog, $stderrLog"
                exit 0
            }
            $process = Get-TrackedProcess
            if (-not $process) { throw "$Service exited during startup; inspect $stdoutLog and $stderrLog." }
            Start-Sleep -Seconds 1
        }
        throw "$Service did not open port $port within $timeout seconds; inspect $stdoutLog and $stderrLog."
    }
    stop {
        $process = Get-TrackedProcess
        if (-not $process) {
            if (Test-Port $port) { throw "Port $port is occupied by an untracked process; refusing to stop it." }
            Write-Output "$Service is already stopped."
            exit 0
        }
        & taskkill.exe /PID $process.ProcessId /T /F | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not stop $Service (pid $($process.ProcessId))." }
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        Write-Output "$Service stopped."
    }
}
