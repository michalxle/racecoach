# RaceCoach

Lokalny system zarządzania stanowiskami **oryginalnego Assetto Corsa** i szkoleniem kierowców.
Wersja MVP: działająca aplikacja z trwałymi danymi, panelem i jawnym trybem demonstracyjnym.
Kod integracji gry i sprzętu wymaga odbioru na docelowych stanowiskach Windows.

> **Jeden komputer z Assetto Corsa (centrala + stanowisko):** dwuklik `START-RaceCoach.bat`,
> potem `PRZYGOTUJ-SCENARIUSZ.bat` — szczegóły w [URUCHOMIENIE-LOKALNE.md](URUCHOMIENIE-LOKALNE.md).

## Uruchomienie na macOS / Linux

Wymagania: Python 3.11+ (zweryfikowany 3.12), Node 22.12+ lub 24/26, npm i Git.

```bash
./scripts/setup.sh
./scripts/run.sh --demo
```

Otwórz **http://127.0.0.1:8000**. Przycisk **Otwórz demonstrację** loguje na jawne konto
`instruktor@demo.local` / `Trening2026!`. Konta kursantów demo: `anna@demo.local`,
`piotr@demo.local`, `lena@demo.local`, z tym samym demonstracyjnym hasłem.

Demo ma dwa stanowiska, trzy konta kursantów, plany, syntetyczny tor i nagrania.
Próby działają w przyspieszonym czasie, mają oddzielne identyfikatory i przechodzą przez
ten sam protokół poleceń, archiwizacji i analizy co integracja rzeczywista.
Wszystkie dane demo są oznaczone; geometria nie przedstawia licencjonowanego toru AC.

Tryb rzeczywisty:

```bash
./scripts/run.sh
```

Przy pierwszym uruchomieniu tworzy konto `instruktor@local` z losowym hasłem zapisanym
w `.local/live/bootstrap.json`. Folder rzeczywistych danych jest oddzielony od demo.
Program odmówi otwarcia folderu danych oznaczonego innym trybem.

## Uruchomienie centrali na Windows

Zainstaluj Python 3.12, Node i Git. W PowerShell, z katalogu repozytorium:

```powershell
.\scripts\setup.ps1
.\scripts\run.ps1 -Demo
# Dla rzeczywistych stanowisk w sieci lokalnej:
.\scripts\run.ps1 -BindAddress 0.0.0.0
```

Na komputerach stanowisk używaj adresu LAN komputera centrali, np. `http://192.168.1.10:8000`.
Zezwól na ten port w regułach sieci prywatnej Windows. Do połączeń przez niezaufaną sieć
potrzebny jest własny reverse proxy HTTPS i `RACECOACH_SECURE_COOKIES=1`.

## Co działa

- Logowanie, sesje z ciasteczkiem HttpOnly, konta kursantów i kontrola dostępu.
- Indywidualne plany z kolejnością sesji, terminem, celem, kryteriami i statusem.
- Niezmienne scenariusze: tor/layout, samochód, warunki, długość i opcjonalny profil DD.
- Rejestracja agenta z indywidualnym tokenem, heartbeat, stan gry i sprzętu.
- Indywidualne i grupowe realizacje: **przygotowanie → gotowość wszystkich → start**.
- Historia każdej próby, ręczne zaliczenie/powtórzenie i notatka instruktora.
- Zapis telemetrii w skompresowanych porcjach; ponowna wysyłka jest idempotentna.
- Mapa 2D, wersjonowane sekcje, dwie linie jazdy i zsynchronizowane wykresy.
- Czasy sekcji, lokalna delta, prędkości i punkt hamowania względem wzorca.
- Trwałe wskazanie okrążenia wzorcowego ćwiczenia; kursant widzi zatwierdzony wzorzec
  bez prywatnej historii i notatek innego kursanta.
- Eksport nagrania JSON i spójna kopia SQLite również przy aktywnym WAL.
- Adapter Windows: konfiguracja/start `acs.exe`, odczyt pamięci AC, lokalna kolejka offline.
- Adapter bazy DD: ponowne wykorzystanie sterowników OpenFFBoard / FFBeast z `wheel-control`.
- Generowanie konfiguracji i uruchamianie osobnej instalacji serwera AC do sesji grupowych.

Panel odświeża podgląd co 1,5 s, a agent komunikuje się z centralą przez HTTP co około sekundę.
Osobny wątek agenta odczytuje grę do 100 razy/s i zapisuje tylko nowe pakiety fizyki.
To odczyt zależny od gry, nie gwarancja 100 nowych próbek każdego kanału.

## Przebieg zajęć

1. **Kursanci:** dodaj konto i początkowe hasło.
2. **Scenariusze:** zaimportuj pakiet toru i dodaj ćwiczenie. Każda zmiana warunków
   powinna tworzyć nowy scenariusz; historia przechowuje własną migawkę.
3. **Plany szkolenia:** utwórz plan osoby i dodaj konkretne sesje.
4. **Stanowiska:** przygotuj sesję, przypisz osoby, stanowiska i zgodne pozycje ich planów.
5. Po potwierdzeniu gotowości wybierz **Start**. Panel pokazuje potwierdzenia agentów.
6. Po przejeździe wybierz **Analiza**, okrążenie i wzorzec, a następnie sekcję toru.
7. Zapisz ocenę i decyzję o zaliczeniu albo ponowieniu. Próby nie są nadpisywane.

Instrukcja stanowiska i granice obecnych adapterów: [Windows i Assetto Corsa](docs/windows-station.md).

## Pierwsza integracja z rzeczywistym stanowiskiem

Poniższa procedura dotyczy oryginalnego **Assetto Corsa 64-bit**, nie ACC ani AC EVO.
Samo uruchomienie gry na stanowisku nie łączy jej z panelem: potrzebny jest agent RaceCoach,
a sesję uruchamia instruktor z panelu. Content Manager nie jest wymagany; podczas tej próby
nie uruchamiaj z niego równolegle gry. Najpierw sprawdź jedną stację i suchy trening indywidualny.

### 1. Przygotuj komputery i zawartość

- **Centrala:** komputer instruktora z Pythonem 3.12, Node 22.12+ oraz Git. Może działać na
  Windows, macOS lub Linux; zarządzany serwer grupowy musi mieć zgodny plik wykonywalny dla systemu.
- **Stanowisko:** Windows, Python 3.12, Git, Steam, zainstalowane AC i wymagane samochody/tory.
  Node nie jest potrzebny do samego agenta. Uruchom wcześniej lokalny przejazd i skonfiguruj
  w grze kierownicę, pedały i przyciski, następnie zamknij grę. Steam pozostaw uruchomiony.
- Komputery muszą mieć połączenie sieciowe ze stałym adresem centrali lub stałą nazwą DNS.
  Przykłady poniżej używają `192.168.1.10`; zastąp go rzeczywistym adresem centrali.
- Na obu komputerach pobierz to samo wydanie RaceCoach. Po otrzymaniu adresu repozytorium:

  ```powershell
  git clone ADRES_REPOZYTORIUM racecoach
  cd racecoach
  git rev-parse --short HEAD
  ```

Repozytorium RaceCoach **nie zawiera** gry, samochodów, torów, CSP ani źródeł `wheel-control`.
Do sterowania bazą skopiuj również osobny, istniejący projekt `wheel-control` na stanowisko,
np. do `C:\sim_soft\wheel-control`. Musi zawierać plik `ddcontrol\core.py` i sterownik danej bazy.
Do pierwszej próby samej gry i telemetrii możesz pominąć zdalne sterowanie DD.

### 2. Uruchom centralę bez demonstracji

Na Windows, w katalogu RaceCoach:

```powershell
.\scripts\setup.ps1
.\scripts\run.ps1 -BindAddress 0.0.0.0
```

Na macOS/Linux:

```bash
./scripts/setup.sh
./scripts/run.sh --host 0.0.0.0
```

Nie dodawaj `-Demo` ani `--demo`. Zaloguj się do `http://192.168.1.10:8000` kontem
`instruktor@local`, używając hasła z `.local/live/bootstrap.json` na centrali. Nie używaj kont demo.
Domyślnie dane i nagrania trafią do `.local/live/`. Przy własnym `RACECOACH_DATA` sprawdź wybrany
folder. Plik `.env.example` jest wzorem; aplikacja nie wczytuje automatycznie pliku `.env`.

Udostępnij port TCP 8000 centrali w zaporze dla właściwej sieci prywatnej. Na stanowisku sprawdź:

```powershell
Invoke-RestMethod http://192.168.1.10:8000/api/health
Invoke-RestMethod http://192.168.1.10:8000/api/meta
```

Oczekiwane wyniki to `status: ok` oraz `demo: False`. Adres `127.0.0.1` na stanowisku wskazywałby
samo stanowisko, nie centralę. Zostaw proces centrali uruchomiony przez całą próbę.

### 3. Zarejestruj i uruchom agenta Windows

Na stanowisku, w katalogu sklonowanego RaceCoach:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e "./agent[hardware]"
```

W panelu wybierz **Stanowiska → Zarejestruj agenta**, nadaj nazwę i zapisz jednorazowo
wyświetlony token. Dla każdego stanowiska utwórz osobną rejestrację i osobny token.
W tej samej konsoli PowerShell na stanowisku uruchom:

```powershell
$env:RACECOACH_AGENT_TOKEN = "TOKEN_TEGO_STANOWISKA"
.venv\Scripts\python.exe -m racecoach_agent `
  --server http://192.168.1.10:8000 `
  --game-dir "C:\Program Files (x86)\Steam\steamapps\common\assettocorsa" `
  --documents "C:\Users\kursant\Documents\Assetto Corsa"
```

Zmień obie ścieżki na rzeczywiste. `--documents` musi wskazywać dokumenty użytkownika Windows,
który uruchamia Steam i grę, także przy przekierowaniu do OneDrive. Token ustawiony w tej konsoli
obowiązuje tylko do jej zamknięcia; nie zapisuj go w repozytorium. Pozostaw agenta uruchomionego.
W panelu stanowisko powinno przejść online i zgłosić stan gry oraz katalog zawartości.

Do włączenia obsługiwanej bazy zatrzymaj agenta przez Ctrl+C i uruchom go ponownie z dodatkowymi
argumentami poniżej, zachowując `--server`, `--game-dir` oraz `--documents` z poprzedniego polecenia:

```powershell
.venv\Scripts\python.exe -m racecoach_agent `
  --server http://192.168.1.10:8000 `
  --game-dir "C:\Program Files (x86)\Steam\steamapps\common\assettocorsa" `
  --documents "C:\Users\kursant\Documents\Assetto Corsa" `
  --hardware openffboard `
  --ddcontrol "C:\sim_soft\wheel-control" `
  --max-strength 25
```

Dla FFBeast użyj `--hardware ffbeast`. Zamknij GUI DD Control / Configurator, aby agent miał
wyłączny dostęp do COM/HID. W panelu sprawdź połączenie bazy, rzeczywisty zakres i siłę oraz
odczyty kontrolerów. Na bezczynnym stanowisku sprawdź zmianę profilu i jego odczyt zwrotny.
Przykładowe `25` jest limitem suwaka w procentach, nie limitem momentu w Nm; dobierz go do
lokalnie zatwierdzonej konfiguracji. Przed jazdą sprawdź lokalne ograniczenia prądu i zatrzymanie
awaryjne. Panel nie zastępuje fizycznego zatrzymania awaryjnego.

### 4. Dodaj rzeczywisty tor i scenariusz

Na stanowisku wyeksportuj geometrię z własnego pliku `ai/fast_lane.ai` w formacie v7:

```powershell
.venv\Scripts\python.exe -m racecoach_agent.track_export `
  --game-dir "C:\Program Files (x86)\Steam\steamapps\common\assettocorsa" `
  --track ID_FOLDERU_TORU --layout ID_FOLDERU_LAYOUTU `
  --name "Tor testowy" --sections 6 --output track.json
```

Podstaw rzeczywiste nazwy folderów z `content\tracks`. Jeśli tor nie ma osobnego layoutu,
pomiń cały argument `--layout`. Przenieś `track.json` na komputer z panelem i w **Scenariusze →
Importuj tor** wprowadź jego zawartość. Przed importem sprawdź nazwy oraz granice sekcji w JSON:
eksporter dzieli tor na równe odcinki postępu, nie rozpoznaje zakrętów. Dokładny format i sposób
wersjonowania opisuje [instrukcja toru](docs/windows-station.md#katalog-i-sekcje-toru).
Bez obsługiwanej linii AI potrzebny jest ręcznie przygotowany pakiet ze zweryfikowaną geometrią.

Dodaj scenariusz z zaimportowanym torem, właściwym layoutem i identyfikatorem auta z
`content\cars`. Na początek ustaw tryb indywidualny, godzinę 12:00, deszcz 0 i identyfikator
istniejącej pogody z `content\weather` (np. `3_clear`, jeśli jest zainstalowana). Wybierz czas
wystarczający na co najmniej dwa pełne okrążenia. Profil DD pozostaw bez zmiany albo wskaż
profil obsługiwany przez bazę, mieszczący się w lokalnym limicie agenta.

### 5. Przeprowadź i oceń próbę

1. W **Kursanci** dodaj rzeczywiste konto testowe. Utwórz plan szkolenia tej osoby i pozycję
   planu z tym scenariuszem, celem oraz kryteriami zaliczenia.
2. W **Stanowiska** przygotuj sesję, przypisując kursanta, stanowisko i właściwą pozycję planu.
   AC musi być zamknięte. Agent sprawdzi zawartość i ewentualny profil DD; poczekaj na gotowość.
3. Wybierz **Start** w panelu. Agent powinien uruchomić `acs.exe`; po załadowaniu potwierdzi
   auto, tor i layout odczytane z gry. Samo przyjęcie polecenia nie potwierdza załadowania sesji.
4. Sprawdź, czy podgląd zmienia prędkość, gaz, hamulec i skręt zgodnie z jazdą. Przejedź co
   najmniej dwa pełne okrążenia od startu do mety. Wyjazd z boksu jest niepełnym okrążeniem;
   przerwane nagranie nie nadaje się do pełnego porównania sekcji.
5. Wybierz **Zakończ**, poczekaj na potwierdzenie agenta i wysłanie danych. Sprawdź zamknięcie
   gry, przywrócenie konfiguracji i zapis próby przy właściwym kursancie oraz pozycji planu.
6. W **Analiza** wybierz pełne okrążenie. Porównaj czas z grą, położenie linii jazdy na mapie,
   moment przejścia granic sekcji, prędkość, gaz, hamulec i skręt. Zapisz zauważone odchylenia.
7. Powtórz ten sam scenariusz. Porównaj nowe okrążenie z wcześniejszym, sprawdź deltę i czasy
   sekcji. Wskaż zatwierdzone okrążenie wzorcowe ćwiczenia; AI eksportuje zarys toru, a wzorzec
   jazdy pochodzi z rzeczywistego nagrania instruktora lub kursanta.
8. Zapisz notatkę oraz zaliczenie/powtórzenie. Zaloguj się osobno jako kursant i sprawdź dostęp
   do własnego planu, prób i zatwierdzonego wzorca.

Odbiór jednej stacji jest zakończony dopiero po potwierdzeniu tych punktów na fizycznym zestawie.
Zapisz wersję RaceCoach (`git rev-parse HEAD`), Windows, AC/CSP, firmware, model bazy, tor/layout,
auto, ustawienia i wynik próby. Lista pozostałych testów: [odbiór MVP](docs/validation.md).

### 6. Sprawdź tryb grupowy i odzyskiwanie połączenia

Po odbiorze jednej stacji skonfiguruj [osobną instalację serwera AC](docs/windows-station.md#zarządzany-serwer-sesji-grupowych)
i zmienne `RACECOACH_SERVER_DIR`, `RACECOACH_SERVER_EXECUTABLE`, `RACECOACH_SERVER_HOST`,
`RACECOACH_SERVER_PORT` **przed uruchomieniem centrali**. Uruchom drugiego agenta z osobnym tokenem.
Zapewnij zgodną zawartość i dostęp do portów TCP/UDP oraz HTTP serwera zgodnie z jego konfiguracją.
Przygotuj sesję grupową, zaczekaj na gotowość wszystkich i sprawdź wspólną jazdę Practice oraz
oddzielne nagrania i wyniki kursantów. Sam panel na porcie 8000 nie zastępuje serwera gry.

W kontrolowanej próbie odłącz sieć stanowiska i połącz ponownie: lokalna gra powinna działać,
panel pokazać brak aktualnego połączenia, a agent dosłać nagranie z kolejki po powrocie sieci.
Sprawdź również odłączenie USB i restart agenta zgodnie z [procedurą awaryjną](docs/windows-station.md#awarie-i-lokalny-bufor).
Stan `unknown` wymaga sprawdzenia lokalnego procesu i konfiguracji, zanim zwolnisz stanowisko.

### Zakres integracji i diagnoza

| Objaw / funkcja | Co sprawdzić lub czego wymaga |
| --- | --- |
| Stanowisko offline | Proces agenta, adres centrali, port/zapora, token właściwego stanowiska; najpierw `/api/health`. |
| Odmowa przygotowania | Dziennik poleceń: zamknij AC, sprawdź identyfikatory auta/toru/layoutu, pogodę oraz profil DD. |
| Brak telemetrii po starcie | Potwierdzenie załadowania gry, AC 64-bit, ten sam użytkownik Steam/agenta i poprawny folder dokumentów. |
| Nieaktywna zmiana profilu / brak bazy | Agent z `--hardware`, osobny `wheel-control`, zależności `[hardware]`, połączenie USB i brak drugiego właściciela COM/HID. |
| Brak porównania lub błędna mapa | Pełne okrążenia bez luk, zgodny tor/layout i wersja geometrii, poprawne granice sekcji względem postępu gry. |
| Zwykła pogoda i pora dnia | Adapter generuje konfigurację początkową; zakres 08:00–18:00. Status `configuration_only` wymaga sprawdzenia w grze, zwłaszcza przy Pure/Sol/CSP. |
| Deszcz / zmiana pogody podczas jazdy | Trening indywidualny: CSP z włączonym WeatherFX na stanowisku — agent instaluje kontroler `racecoach` i zmienia deszcz, mokrość i wodę z potwierdzeniem z gry ([szczegóły](URUCHOMIENIE-LOKALNE.md#co-system-potrafi)). Sesja grupowa: most pogodowy serwera ([kontrakt](docs/windows-station.md#pogoda-i-csp)). Bez CSP agent odmawia startu scenariusza z deszczem. |
| Pedały i kierownica ESP32 | Odczyt osi/przycisków przez WinMM; zdalny zapis parametrów firmware wymaga dodatkowego protokołu i implementacji. |

Testy automatyczne zastępują proces gry i urządzenia obiektami testowymi. **Nie potwierdzają
jeszcze działania na docelowym Windows i fizycznym sprzęcie**; powyższa procedura służy temu odbiorowi.

## Dane i kopie

Domyślne dane demo: `.local/racecoach.sqlite3`. Dane rzeczywiste: `.local/live/racecoach.sqlite3`.
`--data /ścieżka` lub zmienna `RACECOACH_DATA` wybiera inny folder. Dane, tokeny, hasła,
logi i środowiska robocze są wykluczone z Git.

```bash
.venv/bin/python -m racecoach.backup --data .local/live --output .local/backups/szkolenie.sqlite3
```

Kopia zawiera dane kursantów i hashe kont. Przywracaj ją przy zatrzymanym serwerze.
Nie kopiuj samego głównego pliku SQLite w czasie pracy — aktualne dane mogą być w WAL.

## Testy i rozwój

```bash
./scripts/test.sh
# lub osobno:
.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend test
npm --prefix frontend run build
```

Do pracy nad panelem uruchom backend na porcie 8000 i `npm --prefix frontend run dev`.
Vite działa na `http://127.0.0.1:5173` i przekazuje `/api` do centrali.
Strona developerska `/qa/responsive.html` pozwala sprawdzić ten sam panel w 320/375/768/1024 px;
nie wchodzi do kompilacji produkcyjnej.

Dokumentacja endpointów: `/docs` na serwerze. Historia etapów: `git log --oneline`.

## Publikacja repozytorium

Projekt ma historię etapów na gałęzi `main`. Jeśli kopia lokalna nie ma jeszcze zdalnego repozytorium,
utwórz puste repozytorium w swoim hostingu Git (bez inicjalizacji README/licencji) i użyj jego adresu:

```bash
git remote -v
git remote add origin ADRES_REPOZYTORIUM
git push -u origin main
```

Wymagane są uprawnienia zapisu i uwierzytelnienie SSH lub HTTPS hostingu. Jeśli `origin` już
istnieje, zweryfikuj jego adres przed wysyłką; nie dodawaj go ponownie. Jeżeli zdalne repozytorium
ma własne commity, najpierw porównaj historie i uzgodnij ich połączenie — nie używaj `--force`.
Przy kolejnych aktualizacjach wystarczy `git push`. `.local/`, tokeny i nagrania nie są publikowane.

## Architektura i status

```
frontend/                React + TypeScript + Vite
backend/racecoach/       FastAPI, SQLite WAL, konta, sesje i analiza
agent/racecoach_agent/   Windows, shared memory, launcher, USB, kolejka offline
backend/tests/          Testy domeny i protokołu, adapterów i odzyskiwania stanu
frontend/tests/         Testy prezentacji czasu i obsługi błędów HTTP
docs/                   Założenia, analiza wykonalności, instrukcje i odbiór
```

MVP używa jednej bazy SQLite i odpytywania HTTP, co upraszcza lokalne uruchomienie i odzyskiwanie
połączenia. Docelowe PostgreSQL, WebSocket i większą skalę można dołożyć za istniejącymi kontraktami.
Lista w panelu pokazuje maksymalnie 200 ostatnich prób, a dziennik 100 ostatnich poleceń;
zapisane dane pozostają w bazie.

**Przed odbiorem na sprzęcie:** [status weryfikacji i lista prób](docs/validation.md).
Deszcz na rzeczywistym stanowisku, pełna integracja wybranego kontrolera CSP oraz zapisywanie
konfiguracji firmware pedałów i kierownicy ESP32 wymagają dalszej integracji.
Podstawowy agent odrzuca nieobsługiwany scenariusz zamiast zgłaszać pozorny sukces.

Dokumenty [planu](docs/plan-systemu-szkoleniowego.md) i [analizy wykonalności](docs/analiza-integracji-assetto-corsa.md)
zachowują kontekst ustaleń sprzed implementacji; bieżący status opisuje ten README.
