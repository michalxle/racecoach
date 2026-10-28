# RaceCoach na jednym komputerze — szybki start

Ten wariant uruchamia **centralę (panel instruktora)** i **agenta stanowiska** na tym samym
komputerze z Windows i zainstalowanym Assetto Corsa. Wystarczą dwuklikowe pliki `.bat`
w głównym folderze projektu. Pełna dokumentacja systemu jest w [README](README.md).

## Wymagania (jednorazowo)

| Co | Jak zainstalować (PowerShell lub ze strony producenta) |
| --- | --- |
| Python 3.12 (działa też 3.11/3.13) | `winget install Python.Python.3.12` |
| Node.js 22.12+ (LTS) | `winget install OpenJS.NodeJS.LTS` |
| Steam + oryginalne Assetto Corsa (64-bit) | już masz — uruchom grę raz normalnie i skonfiguruj kierownicę/pedały |

Po instalacji Pythona/Node otwórz nowe okno (lub uruchom ponownie Eksplorator), żeby odświeżyć PATH.
Git nie jest potrzebny do uruchomienia.

## Uruchomienie — 3 kroki

1. **Włącz Steam**, a Assetto Corsa zostaw **zamknięte** (grę uruchamia agent).
2. Dwuklik **`START-RaceCoach.bat`**. Przy pierwszym razie skrypt:
   - instaluje zależności (`.venv`, `node_modules`) i buduje panel — kilka minut, tylko raz,
   - wykrywa folder gry w bibliotekach Steam i folder `Dokumenty\Assetto Corsa` (także w OneDrive),
   - uruchamia okno **CENTRALA** (serwer panelu na `http://127.0.0.1:8000`),
   - rejestruje ten komputer jako stanowisko i uruchamia okno **AGENT**,
   - otwiera panel w przeglądarce i wypisuje login `instruktor@local` oraz hasło.
3. Dwuklik **`PRZYGOTUJ-SCENARIUSZ.bat`** (tylko przy pierwszym teście albo dla nowego toru/auta):
   wybierasz tor i auto z listy (wpisz fragment nazwy, np. `vallelunga`, `abarth`), a skrypt
   importuje mapę toru, tworzy ćwiczenie i konto **Kursant testowy** (`kursant@local`, hasło wypisze).

Potem w panelu:

1. **Stanowiska → Przygotuj sesję** — wybierz ćwiczenie, kursanta i stanowisko `Stanowisko <nazwa komputera>`.
2. Poczekaj, aż agent sprawdzi zawartość gry i zgłosi gotowość, kliknij **Start** — agent sam uruchomi AC
   z właściwym autem, torem i warunkami.
3. Przejedź co najmniej **2 pełne okrążenia** (wyjazd z boksu to niepełne okrążenie). W panelu na żywo
   widać prędkość, gaz, hamulec i skręt.
4. Kliknij **Zakończ** — agent zamknie grę, przywróci Twoją konfigurację AC i wyśle nagranie.
5. **Analiza** — wybierz próbę i okrążenie: mapa z linią jazdy, sekcje, delta i wykresy.
   Po kolejnej próbie porównasz okrążenia i ustawisz okrążenie wzorcowe ćwiczenia.

Kolejne uruchomienia: tylko `START-RaceCoach.bat` — instalacja, ścieżki i token stanowiska są zapamiętane.

## Zatrzymywanie

Najpierw okno **AGENT**, potem **CENTRALA** — w każdym naciśnij **Ctrl+C**.
Nie zamykaj okna AGENT krzyżykiem w trakcie sesji: agent nie zdąży przywrócić `cfg\race.ini`.
Jeśli tak się stało, zamknij grę i uruchom **`NAPRAW-KONFIGURACJE-AC.bat`**.

## Pliki `.bat`

| Plik | Do czego służy |
| --- | --- |
| `START-RaceCoach.bat` | Instalacja (za pierwszym razem), centrala, rejestracja stanowiska, agent, przeglądarka. Ponowne uruchomienie przy działającej centrali tylko dołącza brakujące elementy. |
| `PRZYGOTUJ-SCENARIUSZ.bat` | Import toru z Twojej gry (z `ai\fast_lane.ai`), ćwiczenie dla wybranego auta, kursant testowy. Można uruchamiać wielokrotnie dla kolejnych torów/aut. |
| `DEMO-RaceCoach.bat` | Tryb demonstracyjny bez gry: syntetyczne stanowiska, kursanci i nagrania na `http://localhost:8001`. Dobry do obejrzenia wszystkich ekranów, także sesji grupowej. Dane demo są oddzielne od prawdziwych. |
| `NAPRAW-KONFIGURACJE-AC.bat` | Przywraca `Dokumenty\Assetto Corsa\cfg\race.ini` po awaryjnym przerwaniu sesji. |

### Parametry (opcjonalne)

Parametry dopisuje się po nazwie pliku w PowerShell/cmd, np. `START-RaceCoach.bat -Port 8002`.

| Parametr `START-RaceCoach.bat` | Znaczenie |
| --- | --- |
| `-GameDir "D:\...\assettocorsa"` | Folder gry, gdy wykrywanie nie zadziała. Zapamiętywany. |
| `-Documents "D:\...\Assetto Corsa"` | Folder dokumentów AC (z `cfg`). Zapamiętywany. |
| `-Port 8002` | Inny port panelu (gdy 8000 jest zajęty). Podaj ten sam port dla `PRZYGOTUJ-SCENARIUSZ.bat`. |
| `-Hardware openffboard` / `ffbeast` `-DDControl "C:\sim_soft\wheel-control"` `-MaxStrength 25` | Zdalne profile bazy DD przez projekt `wheel-control`. Zamknij wtedy GUI DD Control/Configurator. Bez tego gra używa kierownicy normalnie. |
| `-Lan` | Udostępnia panel w sieci lokalnej (np. tablet instruktora, drugie stanowisko). Wymaga zgody w zaporze. |
| `-NewStation` | Rejestruje stanowisko od nowa (nowy token). |
| `-Rebuild` | Wymusza ponowne zbudowanie panelu. |
| `-NoAgent` / `-NoBrowser` | Bez agenta / bez otwierania przeglądarki. |

| Parametr `PRZYGOTUJ-SCENARIUSZ.bat` | Znaczenie |
| --- | --- |
| `-Track ks_vallelunga -Layout club_circuit -Car abarth500` | Bez pytań — identyfikatory folderów z `content\tracks` i `content\cars`. |
| `-Duration 10` | Długość sesji w minutach (domyślnie 15). |
| `-Sections 8` | Liczba sekcji toru (domyślnie 6, równe odcinki). |
| `-Weather 3_clear -Time 14:30` | Pakiet pogody i godzina (08:00–18:00, bez deszczu). |

## Co system potrafi

**Panel instruktora**
- Konta kursantów z hasłami; kursant loguje się osobno i widzi tylko swój plan, próby i zatwierdzony wzorzec.
- Plany szkolenia: kolejne pozycje (ćwiczenia) z celem, kryteriami zaliczenia, terminem i statusem.
- Scenariusze (ćwiczenia): tor/layout, auto, pogoda, pora dnia, temperatura, przyczepność, czas sesji,
  opcjonalny profil bazy DD (kąt obrotu, siła). Zmiana warunków = nowy scenariusz, historia się nie zmienia.
- Stanowiska: stan online, stan gry, wykryte auta/tory, stan bazy DD i kontrolerów, dziennik poleceń.

**Sesja na stanowisku**
- Przygotowanie → potwierdzenie gotowości → Start → Zakończ; agent sam konfiguruje i uruchamia `acs.exe`,
  sprawdza, czy gra załadowała właściwe auto i tor, a na końcu zamyka grę i przywraca konfigurację.
- Telemetria z pamięci współdzielonej AC (do 100 odczytów/s): prędkość, gaz, hamulec, skręt, pozycja.
- Kolejka offline: gdy zniknie połączenie z centralą, gra działa dalej, a dane są dosłane później.

**Analiza**
- Mapa 2D toru z liniami jazdy dwóch okrążeń, wersjonowane sekcje, zsynchronizowane wykresy.
- Czasy sekcji, delta względem wzorca, prędkości, punkt hamowania.
- Okrążenie wzorcowe ćwiczenia, ocena instruktora (zaliczenie / do powtórzenia + notatka), eksport JSON.
- Kopia bazy: `.venv\Scripts\python.exe -m racecoach.backup --data .local\live --output .local\backups\kopia.sqlite3`.

**Ograniczenia na jednym komputerze**
- Tylko jedno stanowisko (jeden agent na komputer). Sesje grupowe wymagają drugiego komputera i osobnej
  instalacji serwera AC — obejrzysz je w trybie demo.
- Deszcz i zmiana pogody w trakcie jazdy wymagają mostu do CSP — agent odrzuci scenariusz z deszczem.
- Godziny 08:00–18:00. Pure/Sol/CSP mogą nadpisać wygląd pogody (status `configuration_only`).
- Sekcje toru z importu to równe odcinki, nie zakręty — popraw je w JSON (`.local\live\tracks\`),
  zmień `id` i zaimportuj w **Scenariusze → Importuj tor**.

## Gdzie co leży

| Ścieżka | Zawartość |
| --- | --- |
| `.local\live\racecoach.sqlite3` | Baza: konta, plany, próby, telemetria |
| `.local\live\bootstrap.json` | Login i hasło instruktora |
| `.local\live\local-station.json` | Ścieżki gry, ustawienia agenta, token stanowiska, hasło kursanta testowego |
| `.local\live\tracks\*.json` | Wyeksportowane mapy torów |
| `%LOCALAPPDATA%\RaceCoachAgent` | Kolejka offline agenta i kopia `race.ini` na czas sesji |
| `.local\racecoach.sqlite3` | Dane trybu demo |

Folder `.local` nie trafia do Git. Żeby zacząć od zera: zatrzymaj oba okna i usuń `.local\live`.

## Problemy

| Objaw | Rozwiązanie |
| --- | --- |
| „Nie znaleziono Pythona / Brak Node.js” | Zainstaluj (tabela wymagań), otwórz nowe okno, uruchom ponownie. |
| Skrypt nie znajduje gry | `START-RaceCoach.bat -GameDir "ścieżka\assettocorsa"` (folder z `acs.exe`). |
| Centrala nie startuje, zajęty port | `START-RaceCoach.bat -Port 8002` i `PRZYGOTUJ-SCENARIUSZ.bat -Port 8002`. |
| Stanowisko offline | Sprawdź okno AGENT. „Inny agent już działa” — zostało stare okno agenta. |
| „Pozostała kopia konfiguracji…” przy przygotowaniu | Zamknij AC i okno AGENT, uruchom `NAPRAW-KONFIGURACJE-AC.bat`, potem `START-RaceCoach.bat`. |
| „Na stanowisku brakuje auta lub toru” | Agent widzi tylko zawartość z `content\cars` i `content\tracks` tego folderu gry. |
| Gra startuje, ale brak telemetrii | Steam włączony, AC 64-bit, ten sam użytkownik Windows; sprawdź `-Documents`. |
| Tor nie ma na liście | Tor bez `ai\fast_lane.ai` nie da się wyeksportować automatycznie. |
| Polskie znaki w oknach jako „krzaki” | Kosmetyka konsoli; działanie nie jest zagrożone. |
