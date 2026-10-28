# Wspólne funkcje lokalnego uruchomienia: centrala + agent na jednym komputerze z Assetto Corsa.
# Plik jest dołączany przez local-*.ps1; nie uruchamiaj go bezpośrednio.
$ErrorActionPreference = "Stop"
$script:Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script:LiveDir = Join-Path $script:Root ".local\live"
$script:ConfigFile = Join-Path $script:LiveDir "local-station.json"
$script:Python = Join-Path $script:Root ".venv\Scripts\python.exe"

function Write-Step([string]$Text) { Write-Host ""; Write-Host "==> $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host "    $Text" -ForegroundColor Green }
function Write-Info([string]$Text) { Write-Host "    $Text" }
function Write-Warn([string]$Text) { Write-Host "    UWAGA: $Text" -ForegroundColor Yellow }
function Stop-WithError([string]$Text) {
    Write-Host ""
    Write-Host "BŁĄD: $Text" -ForegroundColor Red
    exit 1
}

function Quote-PS([string]$Value) { return "'" + ($Value -replace "'", "''") + "'" }

# ---------- konfiguracja lokalnego stanowiska (.local\live\local-station.json, poza Git) ----------
function Read-LocalConfig {
    if (Test-Path $script:ConfigFile) {
        return (Get-Content $script:ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json)
    }
    return New-Object PSObject
}

function Set-ConfigValue($Config, [string]$Name, $Value) {
    if ($Config.PSObject.Properties[$Name]) { $Config.$Name = $Value }
    else { $Config | Add-Member -NotePropertyName $Name -NotePropertyValue $Value }
}

function Save-LocalConfig($Config) {
    New-Item -ItemType Directory -Force -Path $script:LiveDir | Out-Null
    $json = $Config | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($script:ConfigFile, $json, (New-Object System.Text.UTF8Encoding($false)))
}

# ---------- wykrywanie Assetto Corsa ----------
function Find-AssettoCorsa {
    $candidates = New-Object System.Collections.Generic.List[string]
    try {
        $app = Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 244210" -ErrorAction Stop
        if ($app.InstallLocation) { $candidates.Add($app.InstallLocation) }
    } catch {}
    $steamRoots = @()
    foreach ($key in @("HKCU:\Software\Valve\Steam", "HKLM:\SOFTWARE\WOW6432Node\Valve\Steam", "HKLM:\SOFTWARE\Valve\Steam")) {
        try {
            $item = Get-ItemProperty -Path $key -ErrorAction Stop
            foreach ($name in @("SteamPath", "InstallPath")) {
                if ($item.PSObject.Properties[$name] -and $item.$name) { $steamRoots += ($item.$name -replace "/", "\") }
            }
        } catch {}
    }
    $steamRoots += "C:\Program Files (x86)\Steam"
    foreach ($steam in ($steamRoots | Select-Object -Unique)) {
        $libraries = @($steam)
        $vdf = Join-Path $steam "steamapps\libraryfolders.vdf"
        if (Test-Path $vdf) {
            foreach ($m in [regex]::Matches((Get-Content $vdf -Raw), '"path"\s+"([^"]+)"')) {
                $libraries += ($m.Groups[1].Value -replace "\\\\", "\")
            }
        }
        foreach ($lib in $libraries) { $candidates.Add((Join-Path $lib "steamapps\common\assettocorsa")) }
    }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path (Join-Path $c "acs.exe"))) { return (Resolve-Path $c).Path }
    }
    return $null
}

function Resolve-GameDir([string]$GameDir, $Config) {
    if (-not $GameDir -and $Config.PSObject.Properties["gameDir"]) { $GameDir = $Config.gameDir }
    if ($GameDir -and (Test-Path (Join-Path $GameDir "acs.exe"))) { return (Resolve-Path $GameDir).Path }
    if ($GameDir) { Write-Warn "W '$GameDir' nie ma acs.exe - szukam instalacji automatycznie." }
    $found = Find-AssettoCorsa
    if ($found) { return $found }
    Write-Warn "Nie znalazłem Assetto Corsa w bibliotekach Steam."
    while ($true) {
        $answer = Read-Host "    Podaj folder gry (ten z plikiem acs.exe)"
        $answer = $answer.Trim('"', ' ')
        if ($answer -and (Test-Path (Join-Path $answer "acs.exe"))) { return (Resolve-Path $answer).Path }
        Write-Warn "W tym folderze nie ma acs.exe."
    }
}

function Resolve-Documents([string]$Documents, $Config) {
    if (-not $Documents -and $Config.PSObject.Properties["documents"]) { $Documents = $Config.documents }
    if (-not $Documents) {
        # Uwzględnia przekierowanie Dokumentów do OneDrive.
        $Documents = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Assetto Corsa"
    }
    if (-not (Test-Path (Join-Path $Documents "cfg"))) {
        Write-Warn "Brak '$Documents\cfg'. Uruchom raz grę ze Steam (utworzy ten folder) albo podaj -Documents."
    }
    return $Documents
}

# ---------- instalacja ----------
function Find-SystemPython {
    $ErrorActionPreference = "Continue"
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in @("3.12", "3.13", "3.11")) {
            & py "-$v" -c "import sys" 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return ,@("py", "-$v") }
        }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and $python.Source -notlike "*WindowsApps*") {
        $ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($ver -in @("3.11", "3.12", "3.13")) { return ,@("python") }
    }
    return $null
}

function Test-Node {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Stop-WithError "Brak Node.js. Zainstaluj (np. 'winget install OpenJS.NodeJS.LTS'), otwórz nowe okno i uruchom ponownie."
    }
    $v = (& node --version).TrimStart("v").Split(".")
    if ([int]$v[0] -lt 22 -or ([int]$v[0] -eq 22 -and [int]$v[1] -lt 12)) {
        Stop-WithError "Node $($v -join '.') jest za stary - wymagany 22.12 lub nowszy (winget upgrade OpenJS.NodeJS.LTS)."
    }
}

function Initialize-RaceCoach([switch]$Force) {
    Set-Location $script:Root
    $needPython = $Force -or -not (Test-Path $script:Python)
    $needNode = $Force -or -not (Test-Path (Join-Path $script:Root "frontend\node_modules"))
    if (-not ($needPython -or $needNode)) { return }
    Write-Step "Pierwsza instalacja zależności (jednorazowo, kilka minut)"
    Test-Node
    if ($needPython) {
        if (-not (Test-Path $script:Python)) {
            $sys = Find-SystemPython  # zwraca tablicę (operator , w return) albo $null
            if (-not $sys) {
                Stop-WithError "Nie znaleziono Pythona 3.11-3.13. Zainstaluj np. 'winget install Python.Python.3.12' i uruchom ponownie."
            }
            Write-Info "Tworzę środowisko .venv ($($sys -join ' '))"
            $pyArgs = @($sys | Select-Object -Skip 1) + @("-m", "venv", (Join-Path $script:Root ".venv"))
            & $sys[0] @pyArgs
            if ($LASTEXITCODE -ne 0) { Stop-WithError "Nie udało się utworzyć .venv" }
        }
        & $script:Python -m pip install --disable-pip-version-check -q -r backend\requirements.lock
        if ($LASTEXITCODE -ne 0) { Stop-WithError "Błąd instalacji zależności Pythona" }
        & $script:Python -m pip install --disable-pip-version-check -q --no-deps -e ./backend -e ./agent
        if ($LASTEXITCODE -ne 0) { Stop-WithError "Błąd instalacji pakietów RaceCoach" }
        Write-Ok "Python gotowy"
    }
    if ($needNode) {
        $frontendDir = Join-Path $script:Root "frontend"
        & npm.cmd --prefix $frontendDir ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { Stop-WithError "Błąd 'npm ci'" }
        Write-Ok "Zależności panelu gotowe"
    }
}

function Build-Panel([switch]$Force) {
    $index = Join-Path $script:Root "frontend\dist\index.html"
    $needed = $Force -or -not (Test-Path $index)
    if (-not $needed) {
        $built = (Get-Item $index).LastWriteTime
        $newer = Get-ChildItem (Join-Path $script:Root "frontend\src"), (Join-Path $script:Root "frontend\index.html") -Recurse -File |
            Where-Object { $_.LastWriteTime -gt $built } | Select-Object -First 1
        if ($newer) { $needed = $true }
    }
    if ($needed) {
        Write-Step "Budowanie panelu WWW"
        Test-Node
        $frontendDir = Join-Path $script:Root "frontend"
        # npm.cmd zamiast npm: nakładka npm.ps1 ponownie interpretuje argumenty we własnym zakresie zmiennych.
        & npm.cmd --prefix $frontendDir run build
        if ($LASTEXITCODE -ne 0) { Stop-WithError "Błąd budowania panelu" }
    }
}

# ---------- okna procesów ----------
function Start-PowerShellWindow([string]$Command) {
    $encoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($Command))
    Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encoded | Out-Null
}

# ---------- API centrali ----------
function Test-Server([string]$BaseUrl) {
    try { return ((Invoke-RestMethod -Uri "$BaseUrl/api/health" -TimeoutSec 2).status -eq "ok") } catch { return $false }
}

function Wait-Server([string]$BaseUrl, [int]$Seconds = 60) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Server $BaseUrl) { return $true }
        Start-Sleep -Milliseconds 700
    }
    return $false
}

function Get-HttpStatus($ErrorRecord) {
    try { return [int]$ErrorRecord.Exception.Response.StatusCode } catch { return 0 }
}

function Get-HttpDetail($ErrorRecord) {
    if ($ErrorRecord.ErrorDetails -and $ErrorRecord.ErrorDetails.Message) { return $ErrorRecord.ErrorDetails.Message }
    return $ErrorRecord.Exception.Message
}

function Connect-Panel([string]$BaseUrl) {
    $bootstrap = Join-Path $script:LiveDir "bootstrap.json"
    if (-not (Test-Path $bootstrap)) { Stop-WithError "Brak $bootstrap - centrala nie utworzyła konta instruktora." }
    $credentials = Get-Content $bootstrap -Raw -Encoding UTF8 | ConvertFrom-Json
    $body = @{ email = $credentials.email; password = $credentials.password } | ConvertTo-Json
    try {
        Invoke-RestMethod -Uri "$BaseUrl/api/auth/login" -Method Post -Body $body -ContentType "application/json" -SessionVariable panelSession | Out-Null
    } catch {
        Stop-WithError ("Logowanie kontem z bootstrap.json nie powiodło się: " + (Get-HttpDetail $_))
    }
    return @{ BaseUrl = $BaseUrl; Session = $panelSession; Email = $credentials.email; Password = $credentials.password }
}

function Invoke-Panel($Context, [string]$Method, [string]$Path, $Body = $null) {
    $params = @{ Uri = $Context.BaseUrl + $Path; Method = $Method; WebSession = $Context.Session }
    if ($null -ne $Body) {
        if ($Body -is [string]) { $json = $Body } else { $json = $Body | ConvertTo-Json -Depth 10 }
        $params.Body = [System.Text.Encoding]::UTF8.GetBytes($json)
        $params.ContentType = "application/json; charset=utf-8"
    }
    return Invoke-RestMethod @params
}

# Odczyt nazwy z ui_track.json / ui_car.json (pliki AC bywają niepoprawnym JSON-em, więc regex).
function Get-UiName([string]$File, [string]$Fallback) {
    try {
        if (Test-Path $File) {
            $m = [regex]::Match((Get-Content $File -Raw -Encoding UTF8), '"name"\s*:\s*"([^"]+)"')
            if ($m.Success) { return $m.Groups[1].Value.Trim() }
        }
    } catch {}
    return $Fallback
}
