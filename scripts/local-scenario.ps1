<#
.SYNOPSIS
  Przygotowuje dane do pierwszego testu z lokalnego Assetto Corsa: tor, ćwiczenie (scenariusz) i kursanta testowego.

.DESCRIPTION
  1. Pokazuje tory z linią AI (ai\fast_lane.ai) i eksportuje wybrany do .local\live\tracks\*.json.
  2. Importuje tor do centrali (sekcje = równe odcinki; można je potem zmienić w panelu).
  3. Pozwala wybrać auto i tworzy ćwiczenie: sucho, pogoda 3_clear, 13:00, domyślnie 15 min.
  4. Jeśli w systemie nie ma kursantów, tworzy konto "Kursant testowy".
  Wymaga działającej centrali (START-RaceCoach.bat).

.EXAMPLE
  .\scripts\local-scenario.ps1
.EXAMPLE
  .\scripts\local-scenario.ps1 -Track ks_vallelunga -Layout club_circuit -Car abarth500 -Duration 10
#>
param(
    [string]$Track = "",
    [string]$Layout = "",
    [string]$Car = "",
    [ValidateRange(1, 60)][int]$Sections = 6,
    [ValidateRange(1, 180)][int]$Duration = 15,
    [string]$Weather = "3_clear",
    [string]$Time = "13:00",
    [string]$GameDir = "",
    [int]$Port = 8000
)
. (Join-Path $PSScriptRoot "local-common.ps1")
$Host.UI.RawUI.WindowTitle = "RaceCoach - przygotowanie scenariusza"
Set-Location $Root

function Select-Item($Items, [string]$What) {
    while ($true) {
        $filter = Read-Host "    Wpisz fragment nazwy $What (Enter = pokaż wszystkie)"
        $matched = @($Items | Where-Object { -not $filter -or $_.Label -like "*$filter*" -or $_.Id -like "*$filter*" })
        if ($matched.Count -eq 0) { Write-Warn "Brak wyników dla '$filter'."; continue }
        if ($matched.Count -gt 60) { Write-Warn "$($matched.Count) wyników - zawęź wyszukiwanie."; continue }
        for ($i = 0; $i -lt $matched.Count; $i++) {
            Write-Host ("    {0,3}. {1}  [{2}]" -f ($i + 1), $matched[$i].Label, $matched[$i].Id)
        }
        $choice = Read-Host "    Numer (Enter = szukaj ponownie)"
        $n = 0
        if ([int]::TryParse($choice, [ref]$n) -and $n -ge 1 -and $n -le $matched.Count) { return $matched[$n - 1] }
    }
}

$config = Read-LocalConfig
$GameDir = Resolve-GameDir $GameDir $config
$baseUrl = "http://127.0.0.1:$Port"
if (-not (Test-Server $baseUrl)) { Stop-WithError "Centrala nie działa na $baseUrl. Najpierw uruchom START-RaceCoach.bat." }
$panel = Connect-Panel $baseUrl

# ---------- 1. tor ----------
Write-Step "1/4 Tor"
$tracksRoot = Join-Path $GameDir "content\tracks"
$tracks = @()
foreach ($dir in (Get-ChildItem $tracksRoot -Directory)) {
    if (Test-Path (Join-Path $dir.FullName "ai\fast_lane.ai")) {
        $tracks += [pscustomobject]@{ Track = $dir.Name; Layout = ""; Id = $dir.Name
            Label = (Get-UiName (Join-Path $dir.FullName "ui\ui_track.json") $dir.Name) }
    }
    foreach ($sub in (Get-ChildItem $dir.FullName -Directory)) {
        if (Test-Path (Join-Path $sub.FullName "ai\fast_lane.ai")) {
            $tracks += [pscustomobject]@{ Track = $dir.Name; Layout = $sub.Name; Id = "$($dir.Name)/$($sub.Name)"
                Label = (Get-UiName (Join-Path $dir.FullName "ui\$($sub.Name)\ui_track.json") "$($dir.Name) $($sub.Name)") }
        }
    }
}
if ($Track) {
    $selected = $tracks | Where-Object { $_.Track -eq $Track -and $_.Layout -eq $Layout } | Select-Object -First 1
    if (-not $selected) { Stop-WithError "Tor '$Track' / layout '$Layout' nie istnieje albo nie ma ai\fast_lane.ai." }
} else {
    Write-Info "Znaleziono $($tracks.Count) torów/layoutów z linią AI (potrzebna do mapy toru)."
    Write-Info "Na początek polecam krótki tor, np. Vallelunga Club, Magione, Brands Hatch Indy."
    $selected = Select-Item $tracks "toru"
}
$trackId = $selected.Track
if ($selected.Layout) { $trackId += "--" + $selected.Layout }
$exportDir = Join-Path $LiveDir "tracks"
New-Item -ItemType Directory -Force -Path $exportDir | Out-Null
$exportFile = Join-Path $exportDir "$trackId.json"
$label = $selected.Label
if ($label.Length -lt 2) { $label = $trackId }
$exportArgs = @("-m", "racecoach_agent.track_export", "--game-dir", $GameDir, "--track", $selected.Track,
    "--name", $label, "--sections", "$Sections", "--output", $exportFile)
if ($selected.Layout) { $exportArgs += @("--layout", $selected.Layout) }
& $Python @exportArgs
if ($LASTEXITCODE -ne 0) { Stop-WithError "Eksport toru nie powiódł się (komunikat powyżej)." }

Write-Step "2/4 Import toru do centrali"
try {
    Invoke-Panel $panel "POST" "/api/tracks" ([System.IO.File]::ReadAllText($exportFile, [System.Text.Encoding]::UTF8)) | Out-Null
    Write-Ok "Zaimportowano tor '$label' ($Sections sekcji, id: $trackId)."
} catch {
    if ((Get-HttpStatus $_) -eq 409) { Write-Ok "Tor '$label' był już zaimportowany - używam go." }
    else { Stop-WithError ("Import toru: " + (Get-HttpDetail $_)) }
}

# ---------- 3. auto i ćwiczenie ----------
Write-Step "3/4 Auto i ćwiczenie"
$carsRoot = Join-Path $GameDir "content\cars"
if ($Car) {
    if (-not (Test-Path (Join-Path $carsRoot $Car))) { Stop-WithError "Brak auta '$Car' w $carsRoot." }
    $carItem = [pscustomobject]@{ Id = $Car; Label = (Get-UiName (Join-Path $carsRoot "$Car\ui\ui_car.json") $Car) }
} else {
    $cars = @(Get-ChildItem $carsRoot -Directory | ForEach-Object {
        [pscustomobject]@{ Id = $_.Name; Label = (Get-UiName (Join-Path $_.FullName "ui\ui_car.json") $_.Name) } })
    Write-Info "Znaleziono $($cars.Count) aut. Na początek polecam coś prostego, np. 'abarth', 'mx5', 'gt86'."
    $carItem = Select-Item $cars "auta"
}
if ($carItem.Id -notmatch '^[A-Za-z0-9_.-]+$') { Stop-WithError "Identyfikator auta '$($carItem.Id)' zawiera niedozwolone znaki." }

$weatherRoot = Join-Path $GameDir "content\weather"
if (-not (Test-Path (Join-Path $weatherRoot $Weather))) {
    $fallback = Get-ChildItem $weatherRoot -Directory | Where-Object { $_.Name -match "clear" } | Select-Object -First 1
    if (-not $fallback) { $fallback = Get-ChildItem $weatherRoot -Directory | Select-Object -First 1 }
    if (-not $fallback) { Stop-WithError "Brak pakietów pogody w $weatherRoot." }
    Write-Warn "Brak pogody '$Weather' - używam '$($fallback.Name)'."
    $Weather = $fallback.Name
}
$title = "$label - $($carItem.Label)"
if ($title.Length -gt 140) { $title = $title.Substring(0, 140) }
$exercise = Invoke-Panel $panel "POST" "/api/exercises" @{
    title = $title; track_id = $trackId; car = $carItem.Id; duration = $Duration; mode = "either"
    conditions = @{ weather = $Weather; time = $Time; rain = 0 }
}
Write-Ok "Utworzono ćwiczenie '$title' ($Duration min, $Weather, $Time, sucho)."

# ---------- 4. kursant ----------
Write-Step "4/4 Kursant"
$trainees = @(Invoke-Panel $panel "GET" "/api/trainees" | ForEach-Object { $_ })
if ($trainees.Count -gt 0) {
    Write-Ok ("Kursanci w systemie: " + (($trainees | ForEach-Object { $_.name }) -join ", "))
} else {
    $chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    $password = -join (1..12 | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
    Invoke-Panel $panel "POST" "/api/trainees" @{ name = "Kursant testowy"; email = "kursant@local"; password = $password; notes = "Konto do testów lokalnych" } | Out-Null
    Set-ConfigValue $config "testTraineeEmail" "kursant@local"
    Set-ConfigValue $config "testTraineePassword" $password
    Save-LocalConfig $config
    Write-Ok "Utworzono konto 'Kursant testowy': kursant@local / $password"
}

Write-Host ""
Write-Host "============================ Gotowe ============================" -ForegroundColor Green
Write-Host "  W panelu ($baseUrl):"
Write-Host "   1. Stanowiska -> Przygotuj sesję: ćwiczenie '$title',"
Write-Host "      kursant, stanowisko tego komputera (pozycja planu jest opcjonalna)."
Write-Host "   2. Poczekaj, aż agent potwierdzi gotowość, i kliknij Start - agent sam uruchomi AC."
Write-Host "   3. Przejedź min. 2 pełne okrążenia, w panelu kliknij Zakończ."
Write-Host "   4. Analiza -> wybierz próbę i okrążenie."
Write-Host "  Granice sekcji to równe odcinki - zmienisz je, importując poprawiony JSON:"
Write-Host "  $exportFile (ze zmienionym 'id')."
Write-Host "================================================================" -ForegroundColor Green
