$ErrorActionPreference = 'Stop'
$runtimeDir = Join-Path $PSScriptRoot '.runtime'
foreach ($serviceName in @('frontend','backend')) {
    $statePath = Join-Path $runtimeDir "$serviceName.json"
    if (!(Test-Path -LiteralPath $statePath)) { continue }
    $saved = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $service = Get-Process -Id $saved.id -ErrorAction SilentlyContinue
    if ($service -and [string]$service.StartTime.ToUniversalTime().Ticks -eq [string]$saved.startedTicks -and $service.Path -eq $saved.executable) {
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($service.Id)"
        foreach ($child in $children) {
            if ($child.CommandLine -and $child.CommandLine.Contains($PSScriptRoot)) {
                Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
            }
        }
        Stop-Process -Id $service.Id -ErrorAction SilentlyContinue
        Write-Host "Stopped $serviceName."
    }
    Remove-Item -LiteralPath $statePath
}
