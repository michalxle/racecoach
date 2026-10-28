# Kontrakt centrala–agent v1

Agent inicjuje połączenia HTTP. Token Bearer stanowiska jest oddzielny od ciasteczka
sesji instruktora; w centrali przechowywany jest hash. Każdy komputer otrzymuje własny token.

## Podstawowe endpointy

| Endpoint | Przeznaczenie |
| --- | --- |
| `POST /api/stations` | Instruktor rejestruje stanowisko; token zwracany jeden raz |
| `POST /api/agent/heartbeat` | Wersja, stan gry, sprzęt, możliwości, katalog, aktywna próba i podgląd |
| `GET /api/agent/commands` | Polecenia tego stanowiska w kolejności utworzenia |
| `POST /api/agent/commands/{id}/result` | Przyjęcie/wykonywanie albo terminalny wynik operacji |
| `POST /api/agent/attempts/{id}/telemetry` | Porcja próbek z trwałym identyfikatorem |
| `POST /api/agent/attempts/{id}/finish` | Potwierdzone zakończenie własnej próby |

Pełny schemat walidacji: OpenAPI `/docs` oraz `backend/racecoach/models.py`.

## Sterowanie i potwierdzenia

Polecenie ma `id`, `station_id`, `kind`, `payload`, `created`, `expires` i `status`.
Payload uruchomienia zawiera `run_id`, `attempt_id` oraz migawkę scenariusza.

Obsługiwane operacje: `prepare_session`, `start_session`, `stop_session`, `hardware_profile`.
Przygotowanie ma zwrócić `verified:true`. Gdy wymagany jest profil sprzętu, potrzebny jest
potwierdzony odczyt. Start ma zwrócić `actual` z oczekiwanym `track_id`, `layout`, `car`
i jawnym `simulated`. Niezgodność powoduje odmowę przyjęcia sukcesu.

Statusy poleceń: `queued`, `accepted`, `running`, `succeeded`, `failed`, `rejected`,
`unknown`, `expired`. Powtórzony taki sam wynik jest idempotentny; zmiana terminalnego wyniku
lub danych powtórzenia jest odrzucana. Polecenia są trwale zapisywane lokalnie przed skutkiem ubocznym.

Wygaśnięcia kontroluje centrala również przy nieobecnym agencie. Próba i sesja trafiają
do `attention`, a rezerwacja pozostaje aktywna. Spóźnione potwierdzenie startu nie przywraca
anulowanej sesji. Operator musi doprowadzić do potwierdzonego zatrzymania/uzgodnienia.

Stan połączenia, gry i bazy to osobne informacje. Offline oznacza brak heartbeat dłuższy niż 12 s.
Zlecenie startu wymaga gotowości wszystkich uczestników i aktualnego połączenia.

## Telemetria

Porcja: `chunk_id` i maksymalnie 1000 próbek. Próbki mają rosnące `seq`, niemalejący `t`,
numer okrążenia, postęp 0–1, współrzędne, prędkość, wejścia i wskaźnik jakości.

Ponowna wysyłka identycznej porcji nie duplikuje nagrania. Inna zawartość tego samego
identyfikatora, nakładające się numery i cofający się czas/okrążenie są odrzucane.
Spóźniony bufor może dotrzeć po zakończeniu próby, więc raport należy oceniać po dosłaniu danych.

Dane są kompresowane w SQLite. Agent zachowuje niedostarczone porcje w lokalnej kolejce
i usuwa je dopiero po odpowiedzi serwera. Przy ponownym uruchomieniu nie powtarza niepewnych
akcji startu; zgłasza `unknown` i oznacza poprzednią próbę jako przerwaną.

## Niezmienność historii

Scenariusz i pakiet toru są kopiowane do realizacji. Próba przechowuje tożsamość kursanta,
stanowiska, pozycję planu oraz rzeczywiście potwierdzoną konfigurację.
Zmiana wzorca ćwiczenia nie usuwa dawnych nagrań. Zatwierdzony wzorzec jest udostępniany
kursantom bez prywatnych notatek i identyfikacji innego kursanta.
