# Copy Exolve files from a sibling exolve checkout into exet/ for local dev.
# Usage: .\scripts\link-exolve.ps1 [path-to-exolve]
# Default exolve path: ..\exolve

param(
  [string]$ExolveDir = (Join-Path $PSScriptRoot "..\..\exolve")
)

$ExolveDir = (Resolve-Path $ExolveDir -ErrorAction SilentlyContinue)
if (-not $ExolveDir) {
  Write-Error "Exolve directory not found. Pass path: .\scripts\link-exolve.ps1 C:\path\to\exolve"
  exit 1
}

$ExetDir = Join-Path $PSScriptRoot ".."
$files = @(
  "exolve-m.css",
  "exolve-m.js",
  "exolve-from-puz.js",
  "exolve-from-ipuz.js",
  "exolve-to-puz.js",
  "exolve-to-ipuz.js",
  "exolve-exost.js"
)

foreach ($f in $files) {
  $src = Join-Path $ExolveDir $f
  $dst = Join-Path $ExetDir $f
  if (-not (Test-Path $src)) {
    Write-Warning "Missing in exolve: $f"
    continue
  }
  if (Test-Path $dst) {
    Remove-Item $dst -Force
  }
  Copy-Item $src $dst -Force
  Write-Host "Copied $f"
}

Write-Host "Done. Serve exet with: python -m http.server 8765"
