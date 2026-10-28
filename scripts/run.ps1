param([switch]$Demo, [string]$BindAddress="127.0.0.1", [int]$Port=8000)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
npm --prefix frontend run build
if ($LASTEXITCODE -ne 0) { throw "Błąd budowania panelu" }
$serverArgs = @("-m", "racecoach", "--host", $BindAddress, "--port", "$Port")
if ($Demo) { $serverArgs += "--demo" }
& .venv\Scripts\python.exe @serverArgs
