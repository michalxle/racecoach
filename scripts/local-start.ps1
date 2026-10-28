<#
.SYNOPSIS
  Uruchamia RaceCoach na jednym komputerze: centralę (panel) i agenta stanowiska z lokalnym Assetto Corsa.

.DESCRIPTION
  Przy pierwszym uruchomieniu instaluje zależności, wykrywa folder gry (biblioteki Steam) i folder
  Dokumenty\Assetto Corsa, rejestruje to stanowisko w centrali i zapamiętuje token w
  .local\live\local-station.json (folder wykluczony z Git). Centrala i agent działają w osobnych oknach.

.EXAMPLE
  .\scripts\local-start.ps1
.EXAMPLE
  .\scripts\local-start.ps1 -GameDir "D:\SteamLibrary\steamapps\common\assettocorsa"
.EXAMPLE
  .\scripts\local-start.ps1 -Kiosk -NoOverlayWindow
.EXAMPLE
  .\scripts\local-start.ps1 -Hardware openffboard -DDControl "C:\sim_soft\wheel-control" -MaxStrength 25
#>
param(
    [string]$GameDir = "",
    [string]$Documents = "",
    [int]$Port = 8000,
    [string]$StationName = "",
    [ValidateSet("off", "openffboard", "ffbeast")][string]$Hardware = "",
    [string]$DDControl = "",
    [ValidateRange(0, 100)][int]$MaxStrength = -1,
    [switch]$Lan,
    [switch]$NoAgent,
    [switch]$NoBrowser,
    [switch]$Rebuild,
    [switch]$NewStation,
    [switch]$NoOverlayWindow,
    [switch]$Kiosk
)
. (Join-Path $PSScriptRoot "local-common.ps1")
$Host.UI.RawUI.WindowTitle = "RaceCoach - uruchamianie"
Set-Location $Root

Initialize-RaceCoach
Build-Panel -Force:$Rebuild

# Okno nakładek nad grą korzysta z PySide6 (przeglądarka Qt). Bez niego działają aplikacje RaceCoach w grze.
if (-not $NoAgent -and -not $NoOverlayWindow) {
    $ErrorActionPreference = "Continue"
    & $Python -c "import PySide6.QtWebEngineWidgets" 2>$null
    $hasQt = $LASTEXITCODE -eq 0
    $ErrorActionPreference = "Stop"
    if (-not $hasQt) {
        Write-Step "Instalacja okna nakładek nad grą (PySide6, jednorazowo ok. 300 MB)"
        & $Python -m pip install --disable-pip-version-check -q "PySide6>=6.6"
        if ($LASTEXITCODE -ne 0) { Write-Warn "Nie udało się zainstalować PySide6 - nakładki pokażą się jako aplikacje RaceCoach w grze." }
        else { Write-Ok "Okno nakładek gotowe" }
    }
}

$config = Read-LocalConfig
$baseUrl = "http://127.0.0.1:$Port"
if ($Lan) { $bind = "0.0.0.0" } else { $bind = "127.0.0.1" }

# ---------- ustawienia stanowiska ----------
if (-not $NoAgent) {
    Write-Step "Assetto Corsa na tym komputerze"
    $GameDir = Resolve-GameDir $GameDir $config
    $Documents = Resolve-Documents $Documents $config
    if (-not $Hardware) { if ($config.PSObject.Properties["hardware"]) { $Hardware = $config.hardware } else { $Hardware = "off" } }
    if (-not $DDControl -and $config.PSObject.Properties["ddControl"]) { $DDControl = $config.ddControl }
    if ($MaxStrength -lt 0) { if ($config.PSObject.Properties["maxStrength"]) { $MaxStrength = [int]$config.maxStrength } else { $MaxStrength = 25 } }
    if ($Hardware -ne "off" -and -not (Test-Path (Join-Path $DDControl "ddcontrol\core.py"))) {
        Stop-WithError "Dla -Hardware $Hardware podaj -DDControl z folderem wheel-control (musi zawierać ddcontrol\core.py)."
    }
    Write-Ok "Gra:       $GameDir"
    Write-Ok "Dokumenty: $Documents"
    if ($Hardware -eq "off") { Write-Info "Baza DD:   wyłączona (gra korzysta z kierownicy normalnie; brak zdalnych profili)" }
    else { Write-Ok "Baza DD:   $Hardware, limit suwaka $MaxStrength%, wheel-control: $DDControl" }
    Set-ConfigValue $config "gameDir" $GameDir
    Set-ConfigValue $config "documents" $Documents
    Set-ConfigValue $config "hardware" $Hardware
    Set-ConfigValue $config "ddControl" $DDControl
    Set-ConfigValue $config "maxStrength" $MaxStrength
    Save-LocalConfig $config
    if (-not (Get-Process steam -ErrorAction SilentlyContinue)) { Write-Warn "Steam nie jest uruchomiony - włącz go przed startem sesji (AC wymaga Steam)." }
    if (Get-Process acs -ErrorAction SilentlyContinue) { Write-Warn "Assetto Corsa jest włączone - zamknij grę; sesję uruchamia agent." }
}

# ---------- centrala ----------
Write-Step "Centrala (panel instruktora)"
if (Test-Server $baseUrl) {
    $meta = Invoke-RestMethod "$baseUrl/api/meta"
    if ($meta.demo) { Stop-WithError "Na porcie $Port działa tryb DEMO. Zamknij okno demo albo użyj innego portu (-Port 8002)." }
    Write-Ok "Centrala już działa - używam jej."
} else {
    $command = @"
`$Host.UI.RawUI.WindowTitle = 'RaceCoach - CENTRALA  (Ctrl+C zatrzymuje)'
Set-Location -LiteralPath $(Quote-PS $Root)
Write-Host 'RaceCoach - centrala na $baseUrl (adres nasłuchu: $bind). Nie zamykaj tego okna podczas zajęć.' -ForegroundColor Cyan
& $(Quote-PS $Python) -m racecoach --host $bind --port $Port
Write-Host ''
Write-Host 'Centrala zatrzymana. Możesz zamknąć to okno.' -ForegroundColor Yellow
"@
    Start-PowerShellWindow $command
    Write-Info "Uruchamiam w osobnym oknie CENTRALA..."
    if (-not (Wait-Server $baseUrl 60)) { Stop-WithError "Centrala nie odpowiada po 60 s - sprawdź komunikat w oknie CENTRALA (np. zajęty port: użyj -Port 8002)." }
    Write-Ok "Centrala działa: $baseUrl"
}
$panel = Connect-Panel $baseUrl
Write-Ok "Zalogowano kontem $($panel.Email)"

# ---------- stanowisko i agent ----------
if (-not $NoAgent) {
    Write-Step "Stanowisko (agent na tym komputerze)"
    $station = $null
    if (-not $NewStation -and $config.PSObject.Properties["stationId"] -and $config.PSObject.Properties["stationToken"]) {
        foreach ($s in (Invoke-Panel $panel "GET" "/api/stations")) { if ($s.id -eq $config.stationId) { $station = $s } }
    }
    if ($station) {
        Write-Ok "Stanowisko '$($station.name)' jest już zarejestrowane."
    } else {
        if (-not $StationName) { $StationName = "Stanowisko $env:COMPUTERNAME" }
        $created = Invoke-Panel $panel "POST" "/api/stations" @{ name = $StationName }
        Set-ConfigValue $config "stationId" $created.id
        Set-ConfigValue $config "stationName" $created.name
        Set-ConfigValue $config "stationToken" $created.token
        Save-LocalConfig $config
        Write-Ok "Zarejestrowano nowe stanowisko '$($created.name)' (token zapisany w .local\live\local-station.json)."
    }

    if ($station -and $station.online) {
        Write-Ok "Agent tego stanowiska już działa (online)."
    } else {
        $agentArgs = "--server $(Quote-PS $baseUrl) --game-dir $(Quote-PS $GameDir) --documents $(Quote-PS $Documents)"
        if ($Hardware -ne "off") { $agentArgs += " --hardware $Hardware --ddcontrol $(Quote-PS $DDControl) --max-strength $MaxStrength" }
        if ($NoOverlayWindow) { $agentArgs += " --no-overlay-window" }
        if ($Kiosk) { $agentArgs += " --kiosk" }
        $command = @"
`$Host.UI.RawUI.WindowTitle = 'RaceCoach - AGENT stanowiska  (Ctrl+C zatrzymuje i przywraca konfigurację AC)'
Set-Location -LiteralPath $(Quote-PS $Root)
Write-Host 'RaceCoach - agent stanowiska. Zatrzymuj klawiszami Ctrl+C (nie krzyżykiem), wtedy zamknie grę i przywróci race.ini.' -ForegroundColor Cyan
& $(Quote-PS $Python) -m racecoach_agent $agentArgs
Write-Host ''
Write-Host 'Agent zatrzymany. Możesz zamknąć to okno.' -ForegroundColor Yellow
"@
        # Token trafia do procesu agenta przez dziedziczoną zmienną środowiskową, nie przez wiersz poleceń.
        $env:RACECOACH_AGENT_TOKEN = $config.stationToken
        try { Start-PowerShellWindow $command } finally { Remove-Item Env:RACECOACH_AGENT_TOKEN -ErrorAction SilentlyContinue }
        Write-Info "Uruchamiam w osobnym oknie AGENT..."
        $online = $false
        $deadline = (Get-Date).AddSeconds(30)
        while (-not $online -and (Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 1
            foreach ($s in (Invoke-Panel $panel "GET" "/api/stations")) { if ($s.id -eq $config.stationId -and $s.online) { $online = $true } }
        }
        if ($online) { Write-Ok "Stanowisko jest online." }
        else { Write-Warn "Agent nie zgłosił się w 30 s - sprawdź komunikat w oknie AGENT." }
    }
}

if (-not $NoBrowser) { Start-Process $baseUrl }

Write-Host ""
Write-Host "==================== RaceCoach działa ====================" -ForegroundColor Green
Write-Host "  Panel:  $baseUrl"
Write-Host "  Login:  $($panel.Email)"
Write-Host "  Hasło:  $($panel.Password)"
if ($Lan) { Write-Host "  Z innych komputerów: http://<adres-IP-tego-komputera>:$Port (zezwól na port w zaporze)" }
Write-Host ""
Write-Host "  Scenariusz: Scenariusze -> Nowy scenariusz (tor i auto z listy gry, mapa pobiera się sama)."
Write-Host "  Sesja: Stanowiska -> Przygotuj sesję -> Start. Nakładki w grze startują razem z sesją."
Write-Host "  Układ nakładek: Stanowiska -> Nakładki. Ekran kierowcy: http://127.0.0.1:31399/kiosk"
Write-Host ""
Write-Host "  Okna CENTRALA i AGENT muszą pozostać otwarte. Kończ pracę Ctrl+C - najpierw AGENT, potem CENTRALA."
Write-Host "==========================================================" -ForegroundColor Green
