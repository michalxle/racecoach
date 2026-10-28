# Stanowisko Windows i integracja Assetto Corsa

## Agent

Na stanowisku: Windows, Python 3.12, Steam oraz oryginalne Assetto Corsa 64-bit.
Gra powinna wcześniej działać normalnie z lokalnym kontrolerem i poprawnie skonfigurowanymi wejściami.

Zainstaluj agenta z tego repozytorium:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e "./agent[hardware]"
```

W panelu instruktora wybierz **Stanowiska → Zarejestruj agenta** i zapisz wydany token.
Jest pokazywany tylko raz; w bazie centrali znajduje się jego hash.

```powershell
$env:RACECOACH_AGENT_TOKEN = "TOKEN_Z_PANELU"
.venv\Scripts\python.exe -m racecoach_agent `
  --server http://192.168.1.10:8000 `
  --game-dir "C:\Program Files (x86)\Steam\steamapps\common\assettocorsa" `
  --documents "C:\Users\kursant\Documents\Assetto Corsa"
```

Podaj rzeczywisty folder dokumentów użytkownika gry, również jeśli znajduje się w OneDrive.
Uruchamiaj agenta po zalogowaniu tego samego użytkownika Windows, który uruchamia Steam i grę.
Token nie jest argumentem procesu i nie trafia do logów programu.

Agent raportuje katalog aut i layoutów. Uruchomienie wymaga potwierdzenia zawartości, a następnie
tożsamości gry z pamięci współdzielonej: auto, tor i layout muszą odpowiadać scenariuszowi.
Nie przejmuje już działającego `acs.exe`. Równoległy launcher należy zamknąć.

## Baza DD i kontrolery

Przy obecnym układzie katalogów wskaż sąsiedni projekt `wheel-control`:

```powershell
.venv\Scripts\python.exe -m racecoach_agent `
  --server http://192.168.1.10:8000 `
  --game-dir "C:\Steam\steamapps\common\assettocorsa" `
  --hardware openffboard `
  --ddcontrol "C:\sim_soft\wheel-control" `
  --max-strength 25
```

Alternatywny sterownik: `--hardware ffbeast`. Bez parametru sprzętowego agent działa z
`--hardware off` i nie udostępnia zdalnych zmian bazy.

Agent jest jedynym właścicielem COM/HID. Oryginalne GUI DD Control ani Configurator nie mogą
jednocześnie otwierać tej samej bazy. Lokalnym interfejsem przy działającym agencie jest panel RaceCoach.
Drugą instancję agenta blokuje lokalny port rezerwacyjny 31398.

Zdalny profil zawiera zakres obrotu i procent siły. Zmiana wymaga bezczynnego stanowiska,
niezarezerwowanego przez inną sesję, lokalnego zatwierdzonego limitu i odczytu zwrotnego bazy.
Profil określony w ćwiczeniu jest sprawdzany podczas przygotowania oraz przed startem.
Zmiany dotyczą RAM; brak automatycznego zapisu flash i zdalnych akcji kalibracji, autotestu czy DFU.

`--max-strength` jest lokalną granicą operacyjną suwaka, a nie pełnym ograniczeniem fizycznego
momentu. Target XDrive ma dodatkowe limity prądu i niezależną blokadę końca zakresu.
Muszą być zatwierdzone i przetestowane lokalnie przed udostępnieniem stanowiska kursantowi.
Sygnał `torque` sterownika nie jest bezpośrednim pomiarem momentu w Nm.

Osie i przyciski kontrolerów są odczytywane przez istniejący WinMM. Konfiguracja firmware ESP32
wymaga nowego protokołu, którego obecne kontrolery nie dostarczają.

## Katalog i sekcje toru

Jeśli tor ma linię AI w formacie v7:

```powershell
.venv\Scripts\python.exe -m racecoach_agent.track_export `
  --game-dir "C:\Steam\steamapps\common\assettocorsa" `
  --track ks_nurburgring --layout layout_gp_a `
  --name "Nürburgring GP" --sections 6 --output track.json
```

Parametry są przykładowe — użyj identyfikatorów folderów własnej instalacji.
W panelu **Scenariusze → Importuj tor** wczytaj JSON. Przed zapisaniem zmień nazwy i granice sekcji.
`start` i `end` są pozycjami 0–1, sekcje nie mogą się nakładać. Nowa wersja geometrii/sekcji ma
nowy `id`; pole `game_id` pozostaje identyfikatorem folderu AC. Wersję wyznacza hash pliku AI.

Eksport tworzy geometryczny zarys linii AI, a nie gwarantowaną linię wzorcową instruktora.
Granice pomiarowe należy sprawdzić względem `normalizedCarPosition` gry. Przy braku AI przygotuj
geometrię i JSON z zarejestrowanych współrzędnych lub innego zweryfikowanego źródła.
Pakiet obsługuje geometrię 2D i nie wymaga dołączania modeli KN5 do repozytorium.

## Zarządzany serwer sesji grupowych

Na komputerze centrali przygotuj **oddzielną instalację** serwera AC i poprawny bazowy
`cfg/server_cfg.ini`. RaceCoach ma wyłączne prawo zarządzania tą instalacją.
Nie używaj folderu serwera prowadzonego równocześnie przez inne narzędzie.

```powershell
$env:RACECOACH_SERVER_DIR = "C:\RaceCoachServer"
$env:RACECOACH_SERVER_EXECUTABLE = "C:\RaceCoachServer\acServer.exe"
$env:RACECOACH_SERVER_HOST = "192.168.1.10"
$env:RACECOACH_SERVER_PORT = "9600"
.\scripts\run.ps1 -BindAddress 0.0.0.0
```

Potrzebna jest zgodna zawartość na serwerze i klientach oraz dostępne porty AC TCP/UDP i HTTP
z konfiguracji serwera. Centrala tworzy konfigurację jednej sesji Practice, listę miejsc,
zadany tor, auto, porę dnia, przyczepność i pogodę początkową. Parametr temperatury toru
w konfiguracji serwera jest różnicą względem temperatury powietrza.

Konfiguracja jest kopiowana do folderu danych RaceCoach przed uruchomieniem i przywracana
przy normalnym zatrzymaniu procesu. Nie usuwa ani nie nadpisuje archiwalnych kopii.
W przypadku awarii procesu centrali sprawdź proces serwera i kopie w `server-backups` przed
ponownym użyciem instalacji. Klienci nadal potwierdzają rzeczywiście załadowane auto i tor.

Sesja grupowa jest wspólnym treningiem Practice. Formalne wyścigi, kwalifikacje, kontrola
Steam GUID i import oficjalnych wyników serwera są kolejnym rozszerzeniem.

## Pogoda i CSP

Podstawowy adapter obsługuje lokalne pakiety pogody oraz godziny dzienne 08:00–18:00.
Sprawdza obecność pakietu w `content/weather`. Ustawia zerowy wiatr i wyłącza losową zmianę
przyczepności w generowanej konfiguracji. Nie gwarantuje przejęcia kontroli nad zewnętrznym
kontrolerem Pure/Sol/CSP; aktualne warunki mają status `configuration_only`.

Rzeczywisty deszcz i zmiana warunków podczas jazdy wymagają osobno wdrożonego mostu do
wybranej wersji kontrolera/serwera. RaceCoach ma klienta tego kontraktu:

- środowisko centrali: `RACECOACH_WEATHER_BRIDGE`, `RACECOACH_WEATHER_TOKEN`;
- żądanie: `POST <bridge>/weather`, nagłówek `Authorization: Bearer ...`;
- treść: `{"run_id":"...","rain":0.5,"wetness":0.5,"water":0.1}`;
- odpowiedź po rzeczywistym sprawdzeniu: `{"confirmed":true,...}`.

Brak mostu lub potwierdzenia daje odmowę i zapis w dzienniku. Repozytorium nie zawiera gotowego
pluginu kontrolera CSP i nie oznacza symulacji jako wykonania na rzeczywistym sprzęcie.
Demo jawnie symuluje potwierdzenie polecenia pogodowego. Do odbioru potrzebne jest również
potwierdzenie fizyki deszczu, a nie tylko wyglądu opadów.

## Awarie i lokalny bufor

Agent zapisuje porcje telemetrii i wyniki poleceń w SQLite pod `%LOCALAPPDATA%\RaceCoachAgent`.
Utrata sieci nie przerywa lokalnej gry. Porcje wracają w tej samej kolejności i z tym samym
identyfikatorem. Limit kolejki to 256 MiB; jego osiągnięcie przerywa nagranie i zgłasza błąd,
pozostawiając lokalną grę. Baza ani firmware nie zależą od pętli sieciowej.

Ponowne uruchomienie agenta nie powtarza rozpoczętych operacji. Wynik niepewnego polecenia
ma status `unknown`; timeout centrali zachowuje rezerwację stanowiska do uzgodnienia.
W panelu zleć zakończenie sesji i sprawdź potwierdzenie. Wymuszone zamknięcie nie jest
fizycznym zatrzymaniem awaryjnym — jego działanie musi pozostać lokalne.

Po awarii z pozostawioną kopią `race.ini` zamknij grę i przywróć konfigurację:

```powershell
.venv\Scripts\python.exe -m racecoach_agent `
  --server http://192.168.1.10:8000 --game-dir "C:\Steam\steamapps\common\assettocorsa" `
  --restore-config
```

Przy zwykłym wyłączeniu agenta program kończy własny proces gry i przywraca konfigurację.
Nie zabija gry uruchomionej niezależnie przez użytkownika.
