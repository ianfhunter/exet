# Start the Exet SQLite data API (FastAPI + uvicorn).
$ErrorActionPreference = "Stop"

$Backend = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Backend
$Venv = Join-Path $Backend ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Db = Join-Path $Backend "data\exet.sqlite"
$HostAddr = if ($env:EXET_HOST) { $env:EXET_HOST } else { "127.0.0.1" }
$Port = if ($env:EXET_PORT) { $env:EXET_PORT } else { "8000" }

Set-Location $Root

function Test-VenvPython([string]$PythonExe, [string]$VenvDir) {
    if (-not (Test-Path $PythonExe)) { return $false }
    if (-not (Test-Path (Join-Path $VenvDir "pyvenv.cfg"))) { return $false }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        & $PythonExe -c "import sys" 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $prev
    }
}

if (-not (Test-VenvPython $Python $Venv)) {
    if (Test-Path $Venv) {
        Write-Host "Removing broken virtualenv at backend\.venv (stale paths - recreate after a move) ..."
        try {
            Remove-Item -Recurse -Force $Venv
        } catch {
            Write-Host ""
            Write-Host "Could not delete backend\.venv (server may still be running)."
            Write-Host "Stop uvicorn, then run: .\backend\recreate_venv.ps1"
            Write-Host ""
            throw
        }
    }
    Write-Host "Creating virtualenv at backend\.venv ..."
    python -m venv $Venv
    if (-not (Test-VenvPython $Python $Venv)) {
        throw "Failed to create virtualenv at $Venv"
    }
}

# Use python -m pip (not pip.exe) — pip launchers embed the old venv path after a move.
& $Python -m pip install -q -r (Join-Path $Backend "requirements.txt")

if (-not (Test-Path $Db)) {
    Write-Host "Warning: $Db not found."
    Write-Host "Build it with: backend\.venv\Scripts\python backend\build\build_all.py"
    Write-Host ""
}

Write-Host "Starting Exet data server at http://${HostAddr}:${Port}"
& $Python -m uvicorn backend.main:app --reload --host $HostAddr --port $Port
