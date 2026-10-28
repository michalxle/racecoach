<#
.SYNOPSIS
  Przywraca konfigurację Assetto Corsa (cfg\race.ini) po awaryjnym zamknięciu agenta,
  np. gdy okno AGENT zamknięto krzyżykiem w trakcie sesji. Najpierw zamknij grę i okno AGENT.
#>
param([string]$GameDir = "", [string]$Documents = "")
. (Join-Path $PSScriptRoot "local-common.ps1")
Set-Location $Root
if (-not (Test-Path $Python)) { Stop-WithError "RaceCoach nie jest zainstalowany - uruchom najpierw START-RaceCoach.bat." }
if (Get-Process acs -ErrorAction SilentlyContinue) { Stop-WithError "Assetto Corsa nadal działa - zamknij grę i spróbuj ponownie." }
$config = Read-LocalConfig
$GameDir = Resolve-GameDir $GameDir $config
$Documents = Resolve-Documents $Documents $config
Write-Step "Przywracanie konfiguracji AC"
& $Python -m racecoach_agent --server "http://127.0.0.1" --game-dir $GameDir --documents $Documents --restore-config
if ($LASTEXITCODE -ne 0) { Stop-WithError "Nie udało się przywrócić konfiguracji (komunikat powyżej)." }
Write-Ok "Gotowe. Możesz ponownie uruchomić START-RaceCoach.bat."
