# RaceCoach

Lokalny system zarządzania stanowiskami **oryginalnego Assetto Corsa** i szkoleniem kierowców.
Wersja MVP: działająca aplikacja z trwałymi danymi, panelem i jawnym trybem demonstracyjnym.
Kod integracji gry i sprzętu wymaga odbioru na docelowych stanowiskach Windows.

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
Repozytorium jest lokalne i nie ma skonfigurowanego zdalnego origin.

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
