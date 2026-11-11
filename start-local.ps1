$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$runtimeDir = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
#$pythonExe = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$pythonExe = Join-Path $env:CONDA_PREFIX 'python.exe'
$nodeExe = (Get-Command node.exe -ErrorAction Stop).Source
$viteEntry = Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'
if (!(Test-Path -LiteralPath $pythonExe) -or !(Test-Path -LiteralPath $viteEntry)) {
    throw 'Dependencies are missing. See RUNNING.txt.'
}
$env:PYTHONUTF8 = '1'
function Start-ProjectService($serviceName, $port, $executable, $arguments, $workingDir) {
    $statePath = Join-Path $runtimeDir "$serviceName.json"
    if (Test-Path -LiteralPath $statePath) {
        $saved = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        $existing = Get-Process -Id $saved.id -ErrorAction SilentlyContinue
        if ($existing -and [string]$existing.StartTime.ToUniversalTime().Ticks -eq [string]$saved.startedTicks) {
            Write-Host "$serviceName is already running (PID $($saved.id))."
            return
        }
    }
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($listener) { throw "Port $port is occupied. Stop the other service or choose another port." }
    $service = Start-Process -FilePath $executable -ArgumentList $arguments -WorkingDirectory $workingDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir "$serviceName.out.log") -RedirectStandardError (Join-Path $runtimeDir "$serviceName.err.log")
    @{ id=$service.Id; startedTicks=[string]$service.StartTime.ToUniversalTime().Ticks; executable=$executable } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
    Write-Host "Started $serviceName (PID $($service.Id))."
}
$backendDir = Join-Path $projectRoot 'backend'
$frontendDir = Join-Path $projectRoot 'frontend'
$sourceDir = Join-Path $backendDir 'src'
$envFile = Join-Path $backendDir '.env'
Start-ProjectService 'backend' 8000 $pythonExe @('-m','uvicorn','main:app','--app-dir',('"'+$sourceDir+'"'),'--env-file',('"'+$envFile+'"'),'--host','127.0.0.1','--port','8000') $backendDir
Start-ProjectService 'frontend' 5174 $nodeExe @(('"'+$viteEntry+'"'),'--host','127.0.0.1','--port','5174','--strictPort') $frontendDir
foreach ($address in @('http://127.0.0.1:8000/healthz','http://127.0.0.1:5174/')) {
    $ready = $false
    for ($attempt=0; $attempt -lt 40; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $address -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $ready=$true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (!$ready) { throw "Service did not become ready: $address. Inspect .runtime logs." }
    Write-Host "Ready: $address"
}
Write-Host 'API docs: http://127.0.0.1:8000/docs'
Write-Host 'Real research requires model settings in backend\.env.'
