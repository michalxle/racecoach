$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Nie udało się utworzyć środowiska Python 3.12" }
}
& .venv\Scripts\python.exe -m pip install -r backend\requirements.lock
if ($LASTEXITCODE -ne 0) { throw "Błąd instalacji zależności" }
& .venv\Scripts\python.exe -m pip install --no-deps -e ./backend -e ./agent
if ($LASTEXITCODE -ne 0) { throw "Błąd instalacji RaceCoach" }
npm --prefix frontend ci
if ($LASTEXITCODE -ne 0) { throw "Błąd npm ci" }
npm --prefix frontend run build
if ($LASTEXITCODE -ne 0) { throw "Błąd budowania panelu" }
Write-Output "Gotowe. Uruchom: .\scripts\run.ps1 -Demo"
