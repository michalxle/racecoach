# Odbiór lokalnego MVP

Data: 28 października 2026 r. Środowisko: macOS, Python 3.12, Node 26.12.

## Wykonane sprawdzenia

- 25 testów backendu, domeny i adapterów — pozytywnie.
- 4 testy panelu: zaokrąglanie czasów, znak delty, strefa Europe/Warsaw i obsługa błędów HTTP — pozytywnie.
- TypeScript oraz produkcyjna kompilacja Vite — pozytywnie.
- Start panelu produkcyjnego z jednego serwera na porcie 8000, z zachowaniem istniejącej bazy po aktualizacji.
- Instalacja lokalnych pakietów backendu i agenta, start FastAPI i panelu developerskiego.
- Przeglądarka: logowanie do demo, dwa stanowiska, przygotowanie i start sesji grupowej,
  osobna telemetria i zakończone próby dwóch kursantów.
- Przeglądarka: utworzenie nowego planu, dodanie konkretnej sesji z celem i kryteriami.
- Przeglądarka: porównanie z wybranym wzorcem, wybór nawrotu, zsynchronizowane wykresy,
  zapis oceny i skierowanie do powtórzenia, trwałe wskazanie wzorca ćwiczenia.
- Układ desktop oraz 375 i 320 px, z poprawionymi oznaczeniami mapy i wylogowaniem na telefonie.
- Profil DD w demo: zlecenie 0%, potwierdzenie i ponowne otwarcie formularza z zachowanym 0%; po teście przywrócono 15%.

Testy obejmują również: rozdzielenie uprawnień, anonimowy zatwierdzony wzorzec,
ochronę dostępu do innych prób, powtórne porcje danych, cofający się czas, brakujące próbki,
wyjazd wstecz, barierę gotowości grupy, wygaśnięcie polecenia przy offline,
zachowanie rezerwacji, spóźniony start po anulowaniu, odzyskiwanie lokalnej kolejki,
odczyt zwrotny profilu, izolację demo/live, blokadę drugiego serwera i kopię SQLite z WAL.

Test SDK sprawdza znane offsety struktur AC i UTF-16, a test konfiguracji serwera sprawdza
relatywną temperaturę nawierzchni i odtworzenie oryginalnych plików po zatrzymaniu.
Proces gry i serwera jest w tych testach zastępowany kontrolowanym obiektem testowym.

W użytym zestawie zależności TestClient emituje informację o przyszłej zmianie transportu HTTP;
nie powoduje to błędu testów. Wersje są zapisane w `backend/requirements.lock`.

## Zrzuty z działającego panelu

- [Mapa i wynik sekcji](screenshots/analysis-map.png).
- [Zsynchronizowane wykresy nawrotu](screenshots/analysis-sections.png).
- [Pulpit po uruchomieniu produkcyjnej kompilacji](screenshots/dashboard.png).

Wszystkie pokazane przejazdy są syntetyczne i mają oznaczenie demo.

## Do wykonania na docelowym stanowisku

1. **Gra:** Windows + Steam + AC 1.x 64-bit, poprawna ścieżka dokumentów,
   uruchomienie auta/toru/layoutu i odczyt rzeczywistej tożsamości sesji.
2. **Telemetria:** częstotliwość i opóźnienie odczytów, jednostki i znak skrętu,
   pauza, reset, wyjście z boksu i przejście start/meta. Porównać wynik z czasem gry.
3. **Geometria:** zgodność mapy, postępu i bramek sekcji na konkretnym torze.
   Krzyżujące się trasy i warianty punkt–punkt wymagają osobnego odbioru.
4. **Grupa:** serwer przeznaczony tylko dla RaceCoach, zgodne pliki na dwóch klientach,
   gotowość, dołączanie, indywidualna identyfikacja i zakończenie sesji.
5. **Sprzęt:** prawdziwe CDC/HID OpenFFBoard lub FFBeast, rzeczywisty odczyt zwrotny,
   diagnostyka, odłączenie USB, maksymalny prąd i lokalne ograniczenia bazy.
6. **Awarie:** odłączenie LAN i powrót, restart agenta, przerwanie procesu gry,
   poprawne oznaczenie niekompletnego nagrania i przywrócenie konfiguracji.
7. **Pogoda:** wybrana wersja CSP/kontrolera, implementacja mostu pogodowego,
   potwierdzenie działania na wszystkich klientach oraz wpływu na fizykę nawierzchni.
8. **Pakiet Windows:** uruchomienie skryptów PowerShell i docelowe wdrożenie agenta po zalogowaniu.

Tych prób nie wykonano na macOS. Adaptery nie powinny być traktowane jako zwalidowane
na fizycznym zestawie ani jako gotowy produkt do eksploatacji bez odbioru stanowiska.

## Protokół odbioru fizycznego stanowiska

Wypełnij osobno dla każdego zestawu. Procedura wykonania:
[README — pierwsza integracja](../README.md#pierwsza-integracja-z-rzeczywistym-stanowiskiem).
Ten formularz nie oznacza, że odbiór został już wykonany.

| Środowisko | Wartość |
| --- | --- |
| Data, osoba wykonująca, identyfikator stanowiska | Do uzupełnienia |
| Commit RaceCoach i commit osobnego `wheel-control` | Do uzupełnienia |
| Windows / Python / AC / CSP / kontroler pogody i wersje | Do uzupełnienia |
| Model bazy / firmware / połączenie USB / kontrolery | Do uzupełnienia |
| Lokalny limit siły, limity sterownika i profil DD | Do uzupełnienia |
| Tor / layout / auto / wersja pakietu geometrii | Do uzupełnienia |
| Scenariusz / próba / okrążenie i wzorzec | Do uzupełnienia |

| Sprawdzenie | Wynik i uwagi |
| --- | --- |
| Połączenie agenta, brak oznaczenia demo, odczyt katalogu | Niewykonane |
| Przygotowanie, start i potwierdzona tożsamość gry | Niewykonane |
| Odczyt profilu DD po zmianie i odczyt osi/przycisków | Niewykonane |
| Co najmniej dwa pełne okrążenia, czas AC a RaceCoach | Niewykonane |
| Zgodność mapy i granic każdej sekcji z przejazdem | Niewykonane |
| Porównanie własnych prób i wskazanego wzorca | Niewykonane |
| Notatka, decyzja i widok planu kursanta | Niewykonane |
| Zakończenie, wysłanie danych, przywrócenie konfiguracji | Niewykonane |
| Utrata i powrót sieci, USB oraz restart agenta | Niewykonane |
| Dwa stanowiska: Practice i osobne wyniki | Niewykonane |
| Pogoda początkowa; osobno CSP/deszcz, jeżeli wdrożono | Niewykonane |

Zamiast danych osobowych i tokenów zapisuj identyfikatory techniczne; pełne protokoły z danymi
kursantów przechowuj poza repozytorium. Przy niepowodzeniu dołącz komunikat z dziennika poleceń
bez sekretów oraz opisz oczekiwane i zaobserwowane działanie.

## Świadome granice MVP

- Jeden proces centrali na folder danych; SQLite WAL, HTTP polling, jedna zarządzana instancja serwera grupowego.
- Diagramy i analizy 2D. Brak rendererów KN5/3D ani automatycznej interpretacji wideo/replays.
- Formalna ważność okrążenia nie jest utożsamiana z ciągłością telemetrii; ocena jest zatwierdzana przez instruktora.
- Podstawowy adapter nie dostarcza deszczu ani kontroli Pure/Sol bez dodatkowej integracji.
- Profile DD obejmują zakres i procent siły; firmware pedałów i kierownicy ESP32 nie ma tu kanału zapisu.
- Brak instalatora EXE/MSI, automatycznej dystrybucji modów i pełnego systemu administracji kontami.
- Przyjęto pętle zamknięte; automatyczny podział i ocena tras punkt–punkt są dalszym etapem.

## Odtworzenie sprawdzeń

```bash
./scripts/test.sh
./scripts/run.sh --demo
```

Dla testu układu developerskiego: osobno `npm --prefix frontend run dev`, następnie
`http://127.0.0.1:5173/qa/responsive.html`. Wszystkie testy automatyczne używają folderów
tymczasowych i nie usuwają danych roboczej instalacji.
