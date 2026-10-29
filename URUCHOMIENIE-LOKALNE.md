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

## Uruchomienie

1. **Włącz Steam**, a Assetto Corsa zostaw **zamknięte** (grę uruchamia agent).
2. Dwuklik **`START-RaceCoach.bat`**. Przy pierwszym razie skrypt:
   - instaluje zależności (`.venv`, `node_modules`) i buduje panel — kilka minut, tylko raz,
   - wykrywa folder gry w bibliotekach Steam i folder `Dokumenty\Assetto Corsa` (także w OneDrive),
   - uruchamia okno **CENTRALA** (serwer panelu na `http://127.0.0.1:8000`),
   - rejestruje ten komputer jako stanowisko i uruchamia okno **AGENT**,
   - instaluje okno nakładek nad grą (PySide6, ok. 300 MB, tylko raz; pomiń przez `-NoOverlayWindow`),
   - otwiera panel w przeglądarce i wypisuje login `instruktor@local` oraz hasło.

Potem w panelu:

1. **Kursanci → Dodaj kursanta** (jeśli jeszcze nikogo nie ma).
2. **Scenariusze → Nowy scenariusz** — tor z wariantem i samochód wybierasz z rozwijanych list z
   wyszukiwaniem (wpisz np. `vall club`, `mazda cup`; działa bez polskich znaków). Listy pochodzą z gry na
   stanowisku, z nazwami z plików gry. Mapę toru agent pobiera sam przy zapisie scenariusza. Nazwa
   scenariusza uzupełnia się sama. `PRZYGOTUJ-SCENARIUSZ.bat` nie jest już potrzebny (zostaje jako
   alternatywa z konsoli).
3. **Stanowiska → Przygotuj sesję** — wybierz ćwiczenie, kursanta i stanowisko `Stanowisko <nazwa komputera>`.
   Rodzaj: **trening** na czas albo **wyścig** na liczbę okrążeń.
2. Poczekaj, aż agent sprawdzi zawartość gry i zgłosi gotowość, kliknij **Start** — agent sam uruchomi AC
   z właściwym autem, torem i warunkami.
3. Jedź. W grze widać **nakładki** (delta, czasy, minimapa, wskazówki, instruktor), a w karcie stanowiska
   w panelu: okrążenie, deltę, ostatni i najlepszy czas oraz wskazówki po każdym okrążeniu.
   Przycisk **Wiadomość** wysyła kierowcy tekst do nakładki. Do analizy linii jazdy przejedź
   co najmniej 2 pełne okrążenia (wyjazd z boksu to niepełne okrążenie).
4. Kliknij **Zakończ** — agent zamknie grę, przywróci Twoją konfigurację AC i wyśle nagranie.
5. **Analiza** — wybierz próbę i okrążenie: mapa z linią jazdy, sekcje, delta i wykresy, a niżej lista
   okrążeń zmierzonych przez grę ze wskazówkami trenera. Możesz ustawić okrążenie wzorcowe ćwiczenia.
6. **Rankingi** — najlepsze czasy na każdej kombinacji auta i toru, rekordy osobiste z wykresem postępu,
   wyścigi i osiągnięcia kursanta.

## Nakładki w grze i trener

**Co pokazują** (układ jak w SimTrainer):

| Okienko | Zawartość |
| --- | --- |
| Delta | różnica czasu do wzorca w tym samym miejscu toru, liczona w każdej klatce, z paskiem ±1 s |
| Czasy | bieżące okrążenie (w wyścigu „3/10”), ostatnie (czerwone, gdy nieważne), najlepsze w sesji, rekord kursanta |
| Minimapa | mapa toru z gry (`map.png`) obrócona w kierunku jazdy, z numerami zakrętów |
| Wskazówki | po każdym okrążeniu 1–2 zakręty z największą stratą i przyczyna, np. „Zakręt 3, strata 0,26 s – hamujesz ok. 25 m za wcześnie” |
| Instruktor | cel z planu szkolenia i wiadomości z panelu |

**Wzorzec do delty i wskazówek:** wzorzec ćwiczenia ustawiony w Analizie → rekord kursanta w tym
ćwiczeniu → najlepsze okrążenie bieżącej sesji. W trakcie jazdy wzorzec przesuwa się na każde szybsze
ważne okrążenie. Okrążenie jest nieważne po wyjeździe więcej niż dwoma kołami poza tor albo z boksu.

**Dwa sposoby wyświetlania** (wybierane automatycznie):
- **Okno nad grą** — przezroczyste okno na wierzchu, wygląd jak w panelu. Wymaga gry w **oknie** albo
  **pełnym ekranie bez ramki** (w AC: Opcje → Wideo, wyłącz pełny ekran; w Content Managerze: tryb okna bez ramki).
- **Aplikacje RaceCoach w grze** — gdy gra ma pełny ekran wyłączny (`video.ini`: `FULLSCREEN=1`) albo
  brakuje PySide6. Agent instaluje je w `apps\python\RaceCoach*`. Raz włącz je w grze: pasek aplikacji
  po prawej stronie ekranu podczas jazdy (albo w Content Managerze: Ustawienia → Assetto Corsa → Aplikacje Python).

**Układ okienek:** Stanowiska → **Nakładki** otwiera podgląd; przeciągnij okienka myszą, odznacz
niepotrzebne. Układ zapisuje się w centrali i w ciągu sekundy trafia do gry.

**Ekran kierowcy (kiosk):** `http://127.0.0.1:31399/kiosk` na monitorze stanowiska — kursant, scenariusz,
cel, duży czas okrążenia, delta, wskazówki i wiadomości. `START-RaceCoach.bat -Kiosk` otwiera go
automatycznie w Edge przy starcie sesji (przydatne przy osobnym monitorze stanowiska).

**Wyścig:** w „Przygotuj sesję” wybierz „Wyścig na liczbę okrążeń”. Po ostatnim okrążeniu stanowisko
kończy sesję, a panel pokazuje klasyfikację (okrążenia, łączny czas, strata, najlepsze okrążenie). W trybie
grupowym bez skonfigurowanego serwera AC każdy jedzie na swoim stanowisku (wyścig wirtualny, deszcz działa
lokalnie na każdym stanowisku), z serwerem — na wspólnym torze. Deszcz na wspólnym torze wymaga AssettoServer
(`-AcServer`, [instrukcja](docs/windows-station.md#deszcz-w-sesji-grupowej-assettoserver)).

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
| `NAPRAW-KONFIGURACJE-AC.bat` | Przywraca `cfg\race.ini` i ustawienia pogody CSP (`cfg\extension\weather_fx.ini`) po awaryjnym przerwaniu sesji. |

### Parametry (opcjonalne)

Parametry dopisuje się po nazwie pliku w PowerShell/cmd, np. `START-RaceCoach.bat -Port 8002`.

| Parametr `START-RaceCoach.bat` | Znaczenie |
| --- | --- |
| `-GameDir "D:\...\assettocorsa"` | Folder gry, gdy wykrywanie nie zadziała. Zapamiętywany. |
| `-Documents "D:\...\Assetto Corsa"` | Folder dokumentów AC (z `cfg`). Zapamiętywany. |
| `-Port 8002` | Inny port panelu (gdy 8000 jest zajęty). Podaj ten sam port dla `PRZYGOTUJ-SCENARIUSZ.bat`. |
| `-Hardware openffboard` / `ffbeast` `-DDControl "C:\sim_soft\wheel-control"` `-MaxStrength 25` | Zdalne profile bazy DD przez projekt `wheel-control`. Zamknij wtedy GUI DD Control/Configurator. Bez tego gra używa kierownicy normalnie. |
| `-Lan` | Udostępnia panel w sieci lokalnej (np. tablet instruktora, drugie stanowisko). Wymaga zgody w zaporze. |
| `-AcServer "C:\RaceCoachServer"` | Folder osobnej instalacji serwera do sesji grupowych na wspólnym torze (z `AssettoServer.exe` — także deszcz). Zapamiętywany; używaj z `-Lan`. Wyłączenie: `-NoAcServer`. |
| `-AcServerHost 192.168.x.x` | Adres serwera dla stanowisk, gdy automatyczne wykrycie IP wybierze złą kartę sieciową. |
| `-NewStation` | Rejestruje stanowisko od nowa (nowy token). |
| `-NoOverlayWindow` | Bez okna nakładek nad grą (i bez instalacji PySide6); zostają aplikacje RaceCoach w grze. |
| `-Kiosk` | Przy starcie sesji otwiera ekran kierowcy w Edge na pełnym ekranie. |
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
  opcjonalny profil bazy DD (kąt obrotu, siła). **Edytuj / Usuń** na karcie scenariusza: bez przejazdów zmiana
  jest w miejscu, a usunięcie trwałe; po pierwszym przejeździe zmiana toru, auta lub warunków tworzy nową rewizję
  (stara trafia do archiwum, otwarte pozycje planów przechodzą na nową), a „usunięcie” archiwizuje — historia,
  rekordy i wzorce się nie zmieniają. Archiwum: „Pokaż archiwalne” → **Przywróć**.
- **Szybki przejazd** (Stanowiska lub Scenariusze): tor, auto, warunki i uczestnicy w jednym oknie, bez zapisywania
  scenariusza. Przejazd jest w historii, analizie i rankingach auta+toru, ale nie zaśmieca listy scenariuszy.
- Stanowiska: stan online, stan gry, wykryte auta/tory, stan bazy DD i kontrolerów, dziennik poleceń.

**Sesja grupowa**
- **Kolizje między autami** (przy przygotowaniu sesji grupowej): wyłączone = tryb ducha, auta przenikają się,
  zostają kolizje z torem. Wymaga AssettoServer i CSP na stanowiskach — centrala dopisuje na czas sesji do
  `cfg\csp_extra_options.ini` serwera skrypt CSP pobierany z panelu (`/api/ac/no-collisions.lua`, więc centrala
  musi działać z `-Lan`). Z `acServer.exe` Kunos przygotowanie bez kolizji jest odrzucane.
- **Mapa sesji na żywo**: w Stanowiska → Aktywne sesje mapa toru z kropką i imieniem każdego kierowcy
  (pozycje z telemetrii, ok. 1 raz/s), także w wyścigu wirtualnym.
- **Rywale na minimapie w grze**: niebieskie kropki z imionami pozostałych uczestników w nakładce RaceCoach
  (oknie nad grą). Można to wyłączyć przy przygotowaniu sesji.

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

**Pogoda i deszcz** (wymaga Custom Shaders Patch z włączonym WeatherFX)
- W scenariuszu wybierasz **niebo** (pakiet pogody z gry, np. `3_clear` = Bezchmurnie,
  `7_heavy_clouds` = Duże zachmurzenie) i **deszcz na starcie** w %. Przy deszczu tor jest od startu mokry.
- Podczas jazdy: **Stanowiska → Zmień warunki** — intensywność deszczu, mokrość nawierzchni, stojąca woda
  i czas przejścia (domyślnie 30 s). Zmiana narasta płynnie, a panel potwierdza ją dopiero po odczycie z gry.
- Na czas sesji agent instaluje w grze kontroler pogody `extension\weather-controllers\racecoach` i ustawia go
  w `Dokumenty\Assetto Corsa\cfg\extension\weather_fx.ini`. Po zakończeniu przywraca Twój poprzedni kontroler
  (np. Sol). Bez CSP stanowisko odmówi deszczowego scenariusza zamiast jechać na sucho.

**Ograniczenia na jednym komputerze**
- Tylko jedno stanowisko (jeden agent na komputer). Sesje grupowe wymagają drugiego komputera i osobnej
  instalacji serwera AC — obejrzysz je w trybie demo. Deszcz na wspólnym serwerze wymaga AssettoServer.
- Godziny 08:00–18:00.
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
| „…nie ma Custom Shaders Patch z WeatherFX” | Zainstaluj CSP (np. przez Content Manager) i włącz WeatherFX; agent wykrywa `extension\config\weather_fx.ini` w folderze gry. Uruchom ponownie agenta. |
| „Kontroler pogody RaceCoach nie uruchomił się” | WeatherFX wyłączony albo gra uruchomiona przez Content Managera z innym kontrolerem; sprawdź `cfg\extension\weather_fx.ini` i log CSP. |
| Polskie znaki w oknach jako „krzaki” | Kosmetyka konsoli; działanie nie jest zagrożone. |
| Brak nakładek nad grą | Gra w pełnym ekranie wyłącznym – przełącz na okno/bez ramki albo włącz aplikacje RaceCoach w grze. W oknie AGENT widać, który wariant wybrano. |
| Pusta lista aut i torów w kreatorze | Agent wysyła katalog kilka sekund po starcie; odśwież panel. Okno AGENT: „Wysłano katalog treści gry”. |
| „Tor nie ma linii AI” w kreatorze | Mapy nie da się wygenerować automatycznie; użyj Scenariusze → Importuj tor z przygotowanym plikiem. |
| Delta „—” na pierwszym okrążeniu | Brak wzorca: pierwszy przejazd kursanta tworzy go dopiero po pełnym okrążeniu. |
