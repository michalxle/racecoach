# Wykonalność systemu szkoleniowego na bazie Assetto Corsa

Data analizy: 28 października 2026 r. Zakres: oryginalne Assetto Corsa na Windows, sesje indywidualne i grupowe, plany kursantów, sterowanie scenariuszem, telemetria i analiza sekcji toru.

## 1. Ocena

Założenia są technicznie wykonalne przy zastosowaniu lokalnego agenta na każdym stanowisku i własnego systemu analizy. Najmniej niepewności dotyczy odczytu telemetrii oraz map 2D i porównań przejazdów. Najwięcej prób integracyjnych wymaga sterowanie dynamiczną pogodą i powtarzalność warunków pomiędzy konfiguracjami modów.

To analiza kodu oraz dokumentacji autorów integracji, a nie wynik uruchomienia AC. W tym środowisku nie wykonano testu gry na Windows, serwera AC, CSP ani rzeczywistego sprzętu.

| Wymaganie | Ocena | Droga realizacji i granica |
| --- | --- | --- |
| Wybranie toru i layoutu z panelu | Wykonalne | Agent przygotowuje konfigurację kolejnego uruchomienia; klient musi mieć zgodną zawartość |
| Zmiana toru podczas zajęć | Wykonalne jako przejście do nowej sesji | Zakończenie bieżącej realizacji, konfiguracja, ponowne uruchomienie/dołączenie; bez obietnicy podmiany toru w trwającym przejeździe |
| Zadanie warunków początkowych | Wykonalne | Konfiguracja klienta offline albo serwera grupowego; scenariusz przypięty do wersji integracji |
| Dynamiczna pogoda/deszcz | Warunkowo wykonalne | Konkretny zestaw CSP i kontrolera; AssettoServer oferuje udokumentowane polecenia runtime |
| Zbieranie danych z wielu stanowisk jednocześnie | Wykonalne | Każdy agent odczytuje lokalną grę i wysyła dane z identyfikatorem kursanta i próby |
| Mapa toru w raporcie i podglądzie | Wykonalne | Mapy lokalnej zawartości lub geometria wyznaczona z dostępnych danych |
| Podział na własne sekcje | Wykonalne we własnej aplikacji | Wersjonowane przedziały pozycji na trasie i bramki pomiarowe |
| Porównanie z poprzednią próbą lub wzorcem | Wykonalne | Pełna telemetria obu przejazdów, wspólna oś położenia i zgodny kontekst |
| Automatyczna diagnoza przyczyny błędu | Częściowo | Metryki i reguły wspierają instruktora; sam czas sekcji nie określa przyczyny |
| Zdalne ustawienia bazy DD | Wykonalne w zakresie sterownika | Istniejący kod, jeden właściciel USB, odczyt zwrotny i kontrola stanu |
| Zdalna konfiguracja firmware pedałów/kierownicy | Wymaga rozszerzenia | Obecny odczyt gamepada nie zapewnia zapisu do ESP32 |

## 2. Sterowanie Assetto Corsa z zewnątrz

### Sesje indywidualne

Kod Content Managera pokazuje zapis auta, toru/layoutu, trybu i warunków do konfiguracji `race.ini`. Osobny moduł obsługuje uruchomienie i wynik `race_out.json`. To sprawdzalny punkt zaczepienia dla własnego adaptera. [Konfiguracja CM](https://github.com/gro-ove/actools/blob/master/AcTools/Processes/Game.Properties.cs), [uruchamianie i wynik](https://github.com/gro-ove/actools/blob/master/AcTools/Processes/Game.cs).

Proponowana operacja panelu: instruktor wybiera pozycję planu → agent sprawdza dostępność zawartości → zapisuje zatwierdzony scenariusz → uruchamia grę → odczytuje tożsamość rzeczywistej sesji → centrala oznacza próbę jako rozpoczętą. Zmianę toru projektować jako rozpoczęcie kolejnej realizacji.

Własny serwis agenta powinien zarządzać konfiguracją i procesem gry. Trzeba wybrać i przetestować metodę startu na używanej instalacji Steam, zapobiegać równoczesnym zapisom z lokalnego launchera oraz zachować konfigurację użytkownika. Sam zapis pamięci współdzielonej nie jest proponowaną metodą sterowania.

Content Manager pozostaje narzędziem instalacji i konfiguracji. Nie potwierdzono publicznego, uniwersalnego API CM, które samo realizowałoby cały system szkoleniowy.

### Sesje grupowe

Potrzebny jest zarządzany serwer gry oraz agenci klientów. Standardowy protokół pluginu serwera obejmuje m.in. zdarzenia okrążeń/kolizji i polecenia następnej lub ponownie uruchomionej sesji; jego zakres nie zapewnia pełnego zestawu danych o pedałach kursanta. [Definicja protokołu](https://github.com/gro-ove/actools/blob/master/AcManager.Tools/AcPlugins/Kunos/ACSProtocol.cs).

Panel przygotowuje serwer i listę uczestników, sprawdza ich gotowość i zleca dołączenie. Jedna wspólna instancja ma wspólny tor i scenariusz warunków. Różne ćwiczenia osób mogą korzystać z tej samej instancji, o ile są z nią zgodne. Każda osoba ma własną próbę i własną ocenę.

Odróżnić sesję grupową treningową od formalnego wyścigu. Alternatywny AssettoServer autorzy opisują jako projekt z naciskiem na freeroam, a sesje Race/Qualification jako eksperymentalne. Wybór go do wyścigów wymaga dodatkowego testu. [Repozytorium autora](https://github.com/compujuckel/AssettoServer).

### Pogoda podczas jazdy: konkretna możliwość

AssettoServer dokumentuje `/setweather`, `/setcspweather`, `/setrain`, `/setgrip` oraz zmianę czasu. Pozwala to zaprojektować sterowanie pogodą z panelu poprzez własny adapter. Te polecenia dotyczą AssettoServer; nie stanowią potwierdzenia identycznych możliwości standardowego serwera Kunos. [Polecenia administratora](https://assettoserver.org/docs/next/admin-commands/).

Autor udostępnia też przykład pluginu dodającego własne trasy HTTP. Można na tej podstawie zaprojektować uwierzytelniony most do centrali; gotowego endpointu do naszego panelu trzeba dopiero dostarczyć i przetestować. [SamplePlugin](https://assettoserver.org/docs/next/plugins/SamplePlugin/).

Dla deszczu dokumentacja wymaga odpowiedniego preview CSP i pokazuje możliwość wyłączenia fizyki deszczu przy zachowaniu grafiki. Test szkoleniowy musi zatem osobno potwierdzić wygląd, stan nawierzchni i wpływ na jazdę. [Instrukcja AssettoServer](https://assettoserver.org/docs/next/thebeginnersguide/). CM i CSP są osobnymi projektami. [Informacja autora CM](https://acstuff.club/app/).

W trybie offline zmiana pogody runtime wymaga integracji z wybranym kontrolerem CSP; nie została tu potwierdzona działającym prototypem. Alternatywą projektową jest osobna instancja serwera z jednym kursantem, co ujednolica sterowanie, ale zwiększa liczbę instancji i zmienia sposób prowadzenia sesji. Wybór zależy od wyników próby integracyjnej.

Scenariusz szkoleniowy powinien definiować stałe warunki albo zapisany harmonogram zmian, np. przejście do mokrej nawierzchni w określonym momencie. Rzeczywisty przebieg warunków trzeba zapisać w raporcie. Losowe pogodowe pluginy utrudniają bezpośrednie porównanie prób.

## 3. Zbieranie i monitorowanie danych

### Dane gry

Odczyt pamięci współdzielonej jest stosowany przez Content Managera: osobne bloki physics, graphics i static. Agent odczytuje je lokalnie, a następnie przekazuje centralnemu systemowi. [Implementacja odczytu](https://github.com/gro-ove/actools/blob/master/AcManager.Tools/SharedMemory/AcSharedMemory.cs).

Potwierdzone pola physics obejmują wejścia gazu/hamulca/sprzęgła, skręt, prędkość, bieg, RPM, przeciążenia, poślizgi i wybrane dane opon. [Struktura physics](https://github.com/gro-ove/actools/blob/master/AcManager.Tools/SharedMemory/AcSharedPhysics.cs).

Graphics zawiera współrzędne samochodu, pozycję znormalizowaną na trasie, czasy i sektory, stan pitlane i przyczepność. Static identyfikuje m.in. auto, tor/layout i długość spline. [Graphics](https://github.com/gro-ove/actools/blob/master/AcManager.Tools/SharedMemory/AcSharedGraphics.cs), [static](https://github.com/gro-ove/actools/blob/master/AcManager.Tools/SharedMemory/AcSharedStaticInfo.cs).

Wniosek projektowy: dane wystarczają do mapy pozycji, wykresów wejść i porównań na sekcjach. Nie są gotowym raportem szkoleniowym; obliczenia i interfejs należą do naszego systemu.

### Sprzęt stanowiska

Łączyć dwie warstwy danych: wejścia i stan pojazdu odczytane z gry oraz surowe wejścia/diagnostykę urządzeń odczytane przez istniejące sterowniki. Gra może stosować kalibrację, martwe strefy i krzywe, więc wartości obu warstw trzeba oznaczać oddzielnie.

Aktualny `OpenFFBoardLink._poll` odczytuje `axis.curpos` i `axis.curtorque`, po czym skaluje i ogranicza wynik do `LiveState`. Jest to sygnał raportowany przez sterownik; nie należy przedstawiać go jako zmierzonego momentu na dłoniach w Nm. `MotorXDrive` oferuje osobno prąd `iq`; przeliczenie na moment wymaga zweryfikowanego modelu i kalibracji. Podobnie znormalizowany hamulec nie jest pomiarem siły nacisku w niutonach.

Kod lokalny: [odczyt bazy](../ddcontrol/openffboard/driver.py), [model stanu](../ddcontrol/core.py), [wejścia kontrolerów](../ddcontrol/gamepads.py).

### Częstotliwość i spójność

Roboczy cel do pomiarów: odczyt podstawowych kanałów 50–100 Hz, transmisja podglądu 5–10 Hz i lokalne archiwum w rozdzielczości faktycznie dostępnych danych. To cele własnej implementacji, nie obietnica częstotliwości aktualizacji każdego bloku AC. Physics i graphics mają własne identyfikatory pakietów; rejestrować ich wiek i nie traktować powtórzonego pakietu jako nowego pomiaru.

Dla przykładu przy 200 km/h samochód przemieszcza się ok. 1,11 m w 20 ms. Interpolacja czasów przekroczenia bramek zwiększa użyteczność analiz, lecz nie tworzy dodatkowych rzeczywistych próbek. Dokładność punktu hamowania i linii jazdy należy zmierzyć na docelowym stanowisku.

Osobno obsłużyć pauzę, replay, restart, cofanie, teleport, wyjazd z boksu, niepełne okrążenie i utratę danych. Zanik telemetrii ma status jakości, a nie wartość zero. Zapis lokalny działa podczas utraty połączenia z centralą i jest później dosyłany.

## 4. Wizualizacja toru i linii przejazdu

Panel może pokazywać mapę 2D niezależnie od działającego okna gry. Źródła geometrii należy obsługiwać w trzech poziomach:

1. **Istniejąca mapa:** lokalne `map.png` oraz parametry `data/map.ini`, dobrane do layoutu. Kod innego managera AC pokazuje odczyt obrazu i skali/przesunięć. [Implementacja TrackMapData](https://github.com/JustaPenguin/assetto-server-manager/blob/master/content_tracks.go).
2. **Dane AI:** dostępna linia `fast_lane.ai` może dostarczać punkty do obrysu; parser CM potwierdza współrzędne i dodatkowe szerokości. [Spline](https://github.com/gro-ove/actools/blob/master/AcTools/AiFile/AiSpline.cs), [punkty](https://github.com/gro-ove/actools/blob/master/AcTools/AiFile/AiPoint.cs), [dane dodatkowe](https://github.com/gro-ove/actools/blob/master/AcTools/AiFile/AiPointExtra.cs).
3. **Własny zapis:** punkty ze zweryfikowanego przejazdu można narysować jako przebieg trasy. Taki ślad przedstawia przejechaną linię; pełne granice nawierzchni wymagają dodatkowych danych.

Dostępność i jakość plików sprawdzić dla każdego obsługiwanego toru, zwłaszcza modów. Linia AI służy jako pomoc geometryczna; wzorzec szkoleniowy powinien być osobnym, zatwierdzonym przejazdem.

Agent buduje pakiet toru dla centrali: tożsamość toru/layoutu i wersji, obraz lub geometria, transformacja współrzędnych, kierunek jazdy, położenie startu/mety i definicje sekcji. Zgodność nakładki należy sprawdzić co najmniej na kilku oddalonych punktach toru. Trasy krzyżujące się lub prowadzące na różnych wysokościach wymagają uwzględnienia kolejności i wysokości przy dopasowaniu pozycji.

Widok raportu może pokazywać obie linie jazdy, kolor sekcji zależny od lokalnego zysku/straty i wybrany punkt zsynchronizowany z wykresami. Podgląd na żywo korzysta z tego samego pakietu, z rzadszymi aktualizacjami.

## 5. Sekcje toru i porównania

### Własne sekcje szkoleniowe

Obok sektorów gry przechowywać własny, wersjonowany podział: zakręty, szykany, proste i strefy hamowania. Każda sekcja ma nazwę, początek/koniec na kanonicznej osi trasy, kierunek przejazdu i opcjonalne punkty pomocnicze. Instruktor zatwierdza granice w edytorze mapy.

Granice są stałe dla wszystkich porównywanych prób. Zakręty można dodatkowo opisać fazami: dojazd/hamowanie, wejście, okolica apexu i wyjście. Apex oraz punkt rozpoczęcia hamowania to różne pojęcia i powinny mieć jawne definicje. Wersja granic jest zapisana razem z analizą.

### Wyrównanie przejazdów

Wybrać jeden rzeczywisty przejazd referencyjny: własny wcześniejszy, najlepszy ważny albo wskazany przez instruktora. Wzorzec musi mieć pełną telemetrię. Sama lista czasów albo plik wyniku nie pozwala odzyskać historii gazu i hamulca. Import replays jako pełnego źródła telemetrii wymaga osobnej weryfikacji.

Próbki przypisywać do wspólnej pozycji `s` wzdłuż trasy. Dostępny postęp znormalizowany może być punktem startowym po walidacji; alternatywą jest rzutowanie pozycji na kanoniczną ścieżkę z kontrolą ciągłości. Dystans faktycznie przejechany przez samochód różni się przy innej linii jazdy, dlatego nie wystarczy jako wspólna oś.

Z czasów przekroczenia początku i końca sekcji liczyć:

`czas_sekcji = czas_na_końcu − czas_na_początku`

`delta_sekcji = czas_sekcji_kursanta − czas_sekcji_wzorca`

Dodatnia delta oznacza stratę. Osobno pokazywać skumulowaną deltę od początku okrążenia. Kolor konkretnej sekcji powinien odpowiadać jej własnemu wynikowi, dzięki czemu wcześniejszy błąd nie barwi automatycznie kolejnego poprawnie przejechanego fragmentu. Szarość oznacza brak wiarygodnych danych, a próg neutralny powinien wynikać z jakości pomiaru i przyjętego kryterium.

Obsłużyć granicę okrążenia, sekcje przecinające start/metę oraz trasy punkt–punkt. Przeskoki pozycji, cofanie i niezgodna trasa wykluczają fragment z automatycznego porównania albo wymagają jawnego oznaczenia.

### Metryki sekcji

- czas sekcji i zmiana względem wzorca oraz rozkładu wcześniejszych prób;
- prędkość wejścia, minimum i wyjścia w ustalonych bramkach;
- położenie rozpoczęcia hamowania, szczyt i przebieg zwalniania hamulca;
- przebieg gazu, czas ponownego dodania gazu i okres jazdy bez obu pedałów;
- przebieg skrętu i powtarzalność linii;
- zdarzenia utraty przyczepności lub wyjazdu poza tor, po potwierdzeniu reguł detekcji.

Próg początku hamowania musi mieć ustaloną wartość i histerezę; filtracja i opóźnienia mają być jednakowe dla porównywanych danych. Stwierdzenie „hamowanie rozpoczęte 12 m później” jest obserwacją. Ocena, czy to poprawiło technikę, wymaga także analizy prędkości, linii i wyjścia oraz decyzji instruktora.

Przy porównaniu wielu prób pokazywać trend i rozrzut, nie tylko rekord. Teoretyczne okrążenie złożone z najlepszych sekcji oznaczać jako kompozycję, ponieważ nie zostało przejechane w całości.

## 6. Panel raportu kursanta

Proponowana kolejność informacji:

1. Kursant, pozycja planu, rzeczywista próba, tor/layout, auto, warunki i kompletność nagrania.
2. Wybór wzorca i okrążenia; ostrzeżenie o różnicach konfiguracji wpływających na porównanie.
3. Mapa z oznaczonymi sekcjami i ich deltą, plus obie linie jazdy.
4. Tabela sekcji oraz wybranej historii kursanta: czas, delta, prędkości i zmienność wyników.
5. Zsynchronizowane wykresy prędkości, gazu, hamulca i skrętu względem położenia; kliknięcie sekcji ustawia ten sam zakres.
6. Metryki i notatka instruktora, decyzja o zaliczeniu albo kolejnej próbie.

Możliwe jest porównanie wybranego przejazdu do poprzedniej próby, najlepszego ważnego wyniku albo przejazdu instruktora. Tryb grupowy zachowuje indywidualny raport każdej osoby.

## 7. Warunki rzetelnego porównania

Każda próba wymaga migawki konfiguracji klienta i sprzętu oraz odniesienia do scenariusza. Zapisywać tożsamość i wersję auta/toru, setup, asysty, paliwo i stan opon, warunki oraz ich zmiany, wersje CSP/kontrolera i profil DD. Dane spoza zakresu bazowej telemetrii wymagają dodatkowego odczytu konfiguracji lub adaptera CSP. Parametry żądane i faktycznie potwierdzone mają odrębny status.

Definicja „ważnego okrążenia” jest osobnym elementem integracji. Liczba kół poza trasą i informacja o karze nie powinny automatycznie zastępować dokładnych reguł ważności gry. Trzeba wybrać i sprawdzić źródło: wynik sesji, zdarzenia serwera albo dodatek klienta. Podobnie należy odróżnić uszkodzenie auta od konkretnego zdarzenia kolizji.

Podczas wspólnej jazdy ruch innych aut i kontakt mogą wpływać na wynik; raport powinien oznaczać takie okoliczności, gdy są dostępne. Instruktor może dopuścić porównanie różnych warunków jako ćwiczenie adaptacji, ale system musi pokazać ten kontekst.

## 8. Rekomendowany zakres próby technicznej

Najpierw zweryfikować cały przepływ na jednym torze, jednym aucie i dwóch stanowiskach:

| Próba | Kryterium powodzenia |
| --- | --- |
| Zewnętrzny start | Panel zleca auto/tor/layout i warunki; agent potwierdza rzeczywistą sesję, powtarzalnie po restarcie |
| Rejestracja przejazdu | Poprawna identyfikacja próby/okrążenia, obsługa pauzy i restartu, zmierzona częstotliwość i opóźnienie danych |
| Mapa | Zapisane współrzędne trafiają w odpowiednie miejsca mapy dla całego okrążenia |
| Sekcje | Kilka ręcznie zdefiniowanych sekcji; ich czasy sumują się zgodnie z przyjętą definicją i czasem pełnego okrążenia |
| Wzorzec | Przejechanie dwóch prób; zsynchronizowane wykresy, lokalne delty oraz wybór przejazdu referencyjnego |
| Wspólna sesja | Dwa konta kursantów, jeden serwer i osobne plany/raporty z poprawną identyfikacją uczestników |
| Zmiana pogody | Polecenie runtime, potwierdzenie stanu na obu klientach, oddzielne potwierdzenie wpływu na fizykę i zapis przebiegu warunków |
| Sprzęt | Profil DD zastosowany i odczytany; monitoring wejść gry i urządzeń ma poprawne jednostki oraz źródła |
| Odłączenie sieci | Bieżąca jazda i lokalny zapis trwają; dane są dosłane, a dawne polecenia nie wykonują się ponownie |

Dopiero ten wynik pozwoli potwierdzić parametry jakości i wybrać serwer, kontroler pogody oraz metodę uruchamiania do wdrożenia. Kod CM i przykłady innych projektów wskazują dostępne mechanizmy; nie zastępują testu używanej kombinacji wersji. AssettoServer jest oznaczony przez autora licencją AGPL-3.0, co trzeba uwzględnić przy wyborze i rozszerzaniu komponentu.

Rekomendacja architektoniczna: osobne adaptery `SessionLauncher`, `TelemetryReader`, `TrackCatalog`, `WeatherController`, `MultiplayerServer` i `HardwareController`. Analiza sekcji działa na własnym archiwum danych, niezależnie od launchera. Pozwala to rozwijać panel i modele szkoleniowe bez wiązania ich z konkretnym narzędziem pogody.
