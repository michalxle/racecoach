<#
.SYNOPSIS
  Uruchamia tryb DEMO (syntetyczne stanowiska i dane, bez gry) na http://localhost:8001.
  Dane demo (.local\) są oddzielone od rzeczywistych (.local\live\); oba tryby mogą działać jednocześnie.
#>
param([int]$Port = 8001, [switch]$NoBrowser)
. (Join-Path $PSScriptRoot "local-common.ps1")
$Host.UI.RawUI.WindowTitle = "RaceCoach - demo"
Set-Location $Root
Initialize-RaceCoach
Build-Panel
# "localhost" zamiast 127.0.0.1, żeby ciasteczko logowania demo nie wylogowywało panelu rzeczywistego (8000).
$url = "http://localhost:$Port"
if (Test-Server "http://127.0.0.1:$Port") {
    Write-Ok "Na porcie $Port już coś działa - otwieram przeglądarkę."
} else {
    $command = @"
`$Host.UI.RawUI.WindowTitle = 'RaceCoach - DEMO  (Ctrl+C zatrzymuje)'
Set-Location -LiteralPath $(Quote-PS $Root)
Write-Host 'RaceCoach DEMO na $url - dane syntetyczne, bez gry.' -ForegroundColor Cyan
& $(Quote-PS $Python) -m racecoach --demo --host 127.0.0.1 --port $Port
Write-Host ''
Write-Host 'Demo zatrzymane. Możesz zamknąć to okno.' -ForegroundColor Yellow
"@
    Start-PowerShellWindow $command
    if (-not (Wait-Server "http://127.0.0.1:$Port" 60)) { Stop-WithError "Demo nie wystartowało - sprawdź okno DEMO." }
}
if (-not $NoBrowser) { Start-Process $url }
Write-Host ""
Write-Host "  Demo: $url  ->  przycisk 'Otwórz demonstrację'" -ForegroundColor Green
Write-Host "  Instruktor: instruktor@demo.local / Trening2026!"
Write-Host "  Kursanci:   anna@demo.local, piotr@demo.local, lena@demo.local (to samo hasło)"
