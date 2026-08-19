# Delete and recreate backend/.venv (fixes stale paths after moving the repo).
$ErrorActionPreference = "Stop"

$Backend = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Backend
$Venv = Join-Path $Backend ".venv"

Set-Location $Root

$Port = if ($env:EXET_PORT) { $env:EXET_PORT } else { "8000" }
$listeners = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $listeners) {
    if ($procId -and $procId -ne 0) {
        Write-Host "Stopping process on port ${Port} (PID $procId) ..."
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}

Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match [regex]::Escape($Backend) } |
    ForEach-Object {
        Write-Host "Stopping $($_.ProcessId) ..."
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Start-Sleep -Seconds 1

if (Test-Path $Venv) {
    Write-Host "Removing $Venv ..."
    Remove-Item -Recurse -Force $Venv
}

Write-Host "Creating fresh virtualenv ..."
python -m venv $Venv

$Python = Join-Path $Venv "Scripts\python.exe"
& $Python -m pip install -q -r (Join-Path $Backend "requirements.txt")

Write-Host "Done. Run .\backend\start_server.ps1"
