# Cinema City drop detector — projekt

Data: 2026-08-02
Status: wdrożone i działające. Dokument jest aktualizowany razem z kodem — ostatnia weryfikacja
2026-08-10 (dwie sieci kin, wdrożenie na VPS, tryb pomiarowy).

Plan implementacji w `docs/superpowers/plans/` jest **historycznym zapisem wykonania** i nie jest
aktualizowany. Bieżący stan opisuje ten dokument, a szczegóły wdrożenia `deploy/README.md`.

## Problem

Gdy Cinema City otwiera sprzedaż biletów na wyczekiwany film — publikuje repertuar na kolejny
tydzień albo uruchamia przedsprzedaż premiery — nie ma żadnego powiadomienia. Trzeba ręcznie
odświeżać stronę. Efekt: albo się o tym nie wie i najlepsze miejsca schodzą, albo traci się czas
na cykliczne sprawdzanie.

Cel: proces, który sam pilnuje wskazanych filmów w wskazanych kinach i wysyła wiadomość na
Telegram w momencie, gdy pojawią się nowe seanse.

## Zakres

W zakresie:

- wykrywanie **nowych seansów** dla filmów z listy obserwowanych,
- powiadomienie na Telegram, pogrupowane po filmie i kinie,
- konfiguracja w pliku, edytowana ręcznie,
- dwie sieci kin — Cinema City i Helios — za jednym interfejsem,
- zawężenie wpisu do formatu lub sali (`attributes`),
- obserwacja bez powiadomienia (`notify: false`), żeby zmierzyć godziny publikacji repertuaru.

Poza zakresem (świadomie odrzucone):

- śledzenie zwolnionych miejsc na wyprzedanym seansie,
- alerty progowe od `availabilityRatio`,
- interaktywny bot z komendami `/watch`, `/list` — wymagałby long-pollingu, persystencji
  subskrypcji i obsługi wielu użytkowników,
- kupowanie lub rezerwowanie biletów.

## Rozpoznanie API Cinema City

Ustalenia z realnych zapytań do produkcyjnego API (2026-08-01). Baza:
`https://www.cinema-city.pl/pl/data-api-service/v1/quickbook/10103`

| Endpoint | Zwraca |
|---|---|
| `/cinemas/with-event/until/{data}` | lista kin: `id`, `displayName`, adres, współrzędne |
| `/dates/in-cinema/{kinoId}/until/{data}` | tablica dat, w których kino faktycznie gra |
| `/film-events/in-cinema/{kinoId}/at-date/{data}` | `films[]` + `events[]` na jeden dzień |

Endpointy `/films/with-event/until/{data}` oraz `/film-events/in-cinema/{id}/until/{data}`
zwracają **404** — nie ma sposobu na pobranie wielu dni jednym zapytaniem.

Istotne pola `event`:

```
id, filmId, cinemaId, businessDay, eventDateTime, auditorium,
bookingLink, soldOut, availabilityRatio, attributeIds[]
```

Trzy obserwacje, które kształtują architekturę:

1. **Brak autoryzacji.** Zwykły GET, bez tokenów, kluczy i ciasteczek.
2. **Cloudflare z `cache-control: public, max-age=60`.** Dane żyją na brzegu 60 sekund.
   Odpytywanie częściej niż raz na minutę zwraca bajt w bajt tę samą odpowiedź — 60 s to
   twarde dno sensowności. `cf-cache-status: HIT` potwierdza, że ruch nie dociera do serwerów
   Cinema City. Obecny tryb pomiarowy (cron co minutę) stoi dokładnie na tym dnie; częściej nie
   ma sensu i nigdy nie będzie miało.
3. **Żądania warunkowe są bezużyteczne.** `If-Modified-Since` daje `304` wyłącznie w ciągu 60 s od
   poprzedniego pobrania. Później origin zwraca `200` z **nowym** `Last-Modified`, mimo
   niezmienionego repertuaru — to znacznik wygenerowania odpowiedzi, nie odcisk treści.
   Nagłówka `ETag` nie ma w ogóle. Zmierzone na produkcji:

   ```
   t=0      Last-Modified: 12:04:51
   t=+70s   HTTP 200  LM=12:06:02  cf-cache-status: EXPIRED
   t=+150s  HTTP 200  LM=12:08:32  cf-cache-status: EXPIRED
   ```

   Przy cronie co 5 minut `304` nie wystąpi nigdy, więc **każde pobranie jest bezwarunkowe**.
   Transfer to nie problem — `gzip` sprowadza pełny cykl 35 dni do ok. 650 KB. Problemem byłoby
   utrwalanie `Last-Modified`: zmieniałby się co cykl, plik stanu zmieniałby się co cykl, a
   zabezpieczenie „commit tylko przy realnej zmianie" nigdy by nie zadziałało. Dlatego mechanizmu
   cache'owania nie ma w ogóle.

Konsekwencja dla dopasowywania filmów: film przed premierą **nie istnieje jeszcze** w API, więc nie
ma `filmId`. Obserwowane pozycje są dopasowywane wyłącznie **po nazwie**.

## Rozpoznanie Heliosa

Helios jest drugą siecią i jest **źródłem gorszej klasy** niż Cinema City. Warto to zapisać wprost,
bo z tej różnicy wynika cała ostrożność w `ccdrop/helios.py`.

**Nie ma publicznego API.** `api.helios.pl` istnieje, ale wymaga uwierzytelnienia, więc jest poza
zasięgiem — nie używamy go. Zostaje publiczna strona repertuaru pod adresem
`helios.pl/{miasto}/{kino}/repertuar`.

**Strona nie zwraca JSON-a.** Osadza stan w zminifikowanym IIFE `window.__NUXT__`, czyli w kodzie
JavaScript, nie w danych. Parsowanie regexpem byłoby zgadywaniem, więc blob jest **wykonywany**
przez `qjs` (QuickJS, ok. 1 MB), a z wyniku serializowana jest ścieżka `state.repertoire` albo
`state.core.cinemas`. Node.js odrzucony: ok. 60 MB wobec 1 MB za to samo zadanie, na kontenerze
z 2,9 GB dysku. Bez `qjs` provider nie działa w ogóle — patrz `deploy/README.md`.

**Jedno żądanie na całe kino.** Strona niesie od razu cały horyzont, ok. 32 dni, więc Helios to
dwa żądania na cykl (lista kin ze strony głównej plus repertuar) wobec jednego na każdy grany
dzień w Cinema City. `horizon_days` z konfiguracji tu **filtruje**, a nie rozszerza: przy
horyzoncie 90 dni i tak dostaniemy tyle dni, ile niesie strona.

**Klucz grupy seansów nie zawsze wygląda jak `m<filmId>`.** Ok. 38 % grup ma postać `e<id>` —
to wydarzenia specjalne, RePlay, maratony. Kod kluczuje po polu `_id` obiektu filmu, które zgadzało
się w 100 % przypadków (`m<id>` jest tylko awaryjnym fallbackiem, gdy `_id` nie ma). Założenie
„klucz zaczyna się od `m`" po cichu wyrzuciłoby ponad trzecią repertuaru, i to bez żadnego błędu
w logu.

**Nazwa sali trafia do `attribute_ids`.** `cinemaScreen.feature` (np. `"Dream"`) jest zapisywane
małymi literami razem z `moviePrint.printType`, czyli do tego samego pola, które w Cinema City
wypełnia `attributeIds`. Dlatego `attributes: [dream]` działa **bez nowego pojęcia
w konfiguracji** — jedno pole modelu, dwie zupełnie inaczej opisane sieci.

**Wydarzenia specjalne nie dają atrybutu formatu.** Ich `moviePrint` jest zagnieżdżone pod
`screeningMovies[]`, a nie na poziomie seansu, więc `parse_screening` go nie widzi i takie seanse
mają tylko atrybut sali (albo żadnego). To znana luka, nie błąd: wpis `attributes` po formacie
po prostu ich nie dopasuje.

**Źródło jest nieoficjalne i może się zmienić bez ostrzeżenia.** Przy braku bloba albo nieznanym
kształcie danych provider **loguje, czego brakowało, i zwraca `None`** — nigdy nie zgaduje i nigdy
nie zwraca pustej listy udającej poprawny odczyt. Różnica jest krytyczna: `None` znaczy „nie dało
się zeskanować", więc pary tego kina zostają zimne i nie ma zalewu fałszywych dropów. Pusta lista
znaczyłaby „kino nic nie gra" i przy powrocie strony do normy wysłałaby cały repertuar jako nowy.

## Architektura

Rdzeniem jest czysta funkcja `detect()`. Kluczowe: operuje **wyłącznie** na zbiorze widzianych
seansów, nie na całym pliku stanu.

```
detect(config, seen, pobrane_eventy, kina_kompletne) -> (dropy, aktualizacje_seen)
```

`kina_kompletne` to zbiór **identyfikatorów kin**, które w tym cyklu dały się w ogóle zeskanować,
czyli takich, dla których provider zwrócił listę seansów zamiast `None`. Dla Cinema City znaczy to
„pobrała się lista dat", dla Heliosa „udało się odczytać blob repertuaru". Tylko takie kino może
ocieplić swoją parę przy zimnym starcie. Jednostką jest kino, nie pojedyncza data, bo baseline
wpisu obejmuje cały jego repertuar w danym kinie.

Celowo **nie** wymagamy, by wszystkie daty kina pobrały się bezbłędnie — powód i cena tego wyboru
w sekcji „Zimny start".

Ustawienie flagi `warm` należy do `detect()`, tak samo jak dopasowywanie. `main` decyduje wyłącznie,
czy zwrócone aktualizacje wolno utrwalić.

Bez I/O, bez sieci, bez Telegrama. Cała logika „co jest nowe" jest testowalna bez wychodzenia poza
proces.

```
cinema-city-drop-detector/
├─ config.yaml              # przykładowa konfiguracja; produkcyjna leży poza klonem
├─ ccdrop/
│  ├─ config.py             # wczytanie i walidacja konfiguracji
│  ├─ chains.py             # prefiks sieci w identyfikatorze kina
│  ├─ providers.py          # protokół Provider i rejestr PROVIDERS
│  ├─ api.py                # Cinema City: klient HTTP, throttle, backoff, provider
│  ├─ helios.py             # Helios: strona, qjs, parsowanie, provider
│  ├─ models.py             # dataclasses: Event, WatchEntry, Config, Drop, State
│  ├─ matching.py           # dopasowanie po nazwie i po wyrażeniu regularnym
│  ├─ detector.py           # czysta logika diffowania
│  ├─ notifier.py           # formatowanie wiadomości i wysyłka
│  ├─ schedule.py           # czy ta minuta mieści się w oknie
│  ├─ state.py              # odczyt, zapis, przycinanie stanu
│  └─ main.py               # spięcie powyższych, reguły zapisu stanu
├─ tools/
│  ├─ get_chat_id.py        # wypisuje TELEGRAM_CHAT_ID z getUpdates
│  ├─ list_cinemas.py       # wypisuje identyfikatory i nazwy kin Cinema City
│  ├─ list_helios_cinemas.py # to samo dla Heliosa
│  └─ drop_hours.py         # rozkład godzin wykrycia z drop_log
├─ deploy/                  # wdrożenie: cron na Alpine, unity systemd na zapas
├─ tests/
└─ .github/workflows/check.yml   # historyczny, wyłączony
```

Granice: `detector` nie wie nic o HTTP ani o Telegramie, providery nie wiedzą nic o obserwowanych
filmach, `notifier` dostaje gotową listę dropów i tylko ją formatuje. Decyzje o tym, **co wolno
utrwalić**, podejmuje wyłącznie `main`.

### Providery

Pobieranie schodzi za wąski protokół w `ccdrop/providers.py`:

```python
class Provider(Protocol):
    def fetch(self, cinema_id: str, today: str, horizon_days: int) -> list[Event] | None: ...
    def cinema_names(self, today: str, horizon_days: int) -> dict[str, str]: ...
```

Dwie metody, bo tylko tyle potrzebuje `main`: seanse jednego kina i nazwy kin do treści
powiadomienia. Rejestr `PROVIDERS` mapuje nazwę sieci na fabrykę providera, więc **dodanie sieci
to jeden wpis w rejestrze** plus moduł z implementacją — `detect`, `notifier`, `state` i reguły
utrwalania zostają nietknięte.

Najważniejszy element kontraktu to **`None` z `fetch`**. Znaczy „tego kina nie dało się w tym cyklu
zeskanować w ogóle" i jest jedynym sposobem, w jaki kino wypada z `kina_kompletne`. Zimne pary
tego kina zostają zimne, a jego seanse nie wchodzą do diffu — nie ma więc ani fałszywych dropów,
ani cichego skasowania baseline'u. Pusta lista to coś zupełnie innego: poprawnie odczytane „nic nie
gra". Provider, który po awarii zwróciłby `[]` zamiast `None`, złamałby zimny start.

Rozróżnienie kosztuje jedno pytanie na provider: co u mnie znaczy „nie udało się zeskanować".
W Cinema City to nieudana lista dat (pojedyncza nieudana data to nie awaria kina — patrz „Zimny
start"), w Heliosie brak bloba `window.__NUXT__` albo nieznany kształt danych.

### Identyfikatory kin z prefiksem sieci

Identyfikator kina nosi prefiks sieci: `cc:1060`, `helios:warszawa/kino-helios-blue-city`.
Wartość bez prefiksu normalizuje się do `cc`, żeby stare konfiguracje i przykłady dalej działały.
Nieznany prefiks jest odrzucany przy wczytywaniu konfiguracji, a nie dopiero przy pobieraniu.

Prefiks jest obowiązkowy, bo numery kin nie są globalnie unikalne — dwie sieci mogą użyć tego
samego identyfikatora, a wtedy klucze `watch_state` i `cinema_names` zaczęłyby się zlewać
i pary jednej sieci ocieplałyby pary drugiej.

Postać z prefiksem przechodzi przez `Event.cinema_id`, klucze `watch_state` i `cinema_names`, więc
w całym przepływie jest **jedna** reprezentacja. Provider ściąga prefiks przed żądaniem
(`local_id`) i stempluje go z powrotem na zwracanych danych (`prefixed`), dzięki czemu żaden kod
poniżej providerów nie kroi stringów. Pomocniki są w `ccdrop/chains.py` — jedynym miejscu, które
wie o istnieniu dwukropka.

## Model stanu

Plik `seen.json` w katalogu wskazanym przez `--state-dir`, trzy niezależne sekcje:

```json
{
  "version": 1,
  "watch_state": {
    "Odyseja|cc:1060|imax": {
      "warm": true,
      "seen_events": { "1600867": "2026-08-15" }
    }
  },
  "cinema_names": { "cc:1060": "Warszawa - Sadyba" },
  "drop_log": [
    {
      "detected_at": "2026-08-03T09:01:12+02:00",
      "film": "Odyseja",
      "cinema": "cc:1060",
      "count": 3,
      "notified": true
    }
  ]
}
```

Każda zmienia się wyłącznie wtedy, gdy zmieni się repertuar. To był warunek konieczny, by
zabezpieczenie „commit tylko przy realnej zmianie" na gałęzi `state` w ogóle działało — dlatego
w stanie **nie ma** żadnego znacznika ostatniego uruchomienia, choć bywa kuszący. Na VPS-ie stan
nie idzie już do gita, ale reguła zostaje: plik, który zmienia się co minutę, nie da się czytać
diffem, a znacznik czasu i tak niczego nie rozstrzyga, czego nie widać w logu.

`drop_log` służy do pomiaru: zapisuje moment wykrycia grupy w strefie Europe/Warsaw. Cel jest
konkretny — ustalić, o których godzinach kina faktycznie publikują nowe seanse, zamiast zgadywać
przy wyborze okna odpytywania. Znacznik musi być warszawski, nie UTC; host bywa ustawiony na UTC
(runner GHA zawsze był), więc zapis `07:01Z` zamiast `09:01+02:00` przesunąłby cały rozkład
o dwie godziny.

Wpis powstaje **po udanej wysyłce**, nie w momencie wykrycia. Inaczej nieudana wysyłka logowałaby
ten sam drop w każdym kolejnym cyklu i wykrzywiła pomiar. Wyjątkiem są wpisy `notify: false`,
gdzie nie ma wysyłki, która mogłaby zawieść — patrz „Obserwacja bez powiadomienia".

**Pole `notified`** odróżnia realne dostarczenie od cichej obserwacji. Bez niego jeden wpis
łapiący cały repertuar zalałby rejestr i rozkład godzin przestałby cokolwiek mówić
o powiadomieniach. `tools/drop_hours.py` raportuje obie grupy **osobno**, a wpisy sprzed dodania
pola traktuje jako powiadamiające — starsze rejestry powstawały wyłącznie z dostarczeń, więc to
odtworzenie faktu, nie domysł.

**Kluczem `watch_state` jest trójka (wartość `match` × identyfikator kina × zbiór `attributes`).**
Nie sam wpis `watch` — bo dopisanie kina do globalnej listy `cinemas` nie tworzy nowego wpisu,
a para (film × nowe kino) jest w całości nieznana i bez tego klucza zalałaby skrzynkę całym
bieżącym repertuarem tego kina. Atrybuty wchodzą do klucza, bo zawężają zbiór pasujących seansów:
ten sam `match` z `attributes: [imax]` i bez atrybutów to dwa różne baseline'y, a wspólny klucz
sprawiłby, że węższy wpis „widziałby" seanse, których nigdy nie zgłosił. Atrybuty są w kluczu
posortowane, więc kolejność w YAML-u nie tworzy nowego klucza.

Zmiana tekstu w `match` tworzy nowy klucz, czyli świadomie wywołuje zimny start. Jest to zachowanie
pożądane: inny `match` to inne zapytanie. To samo dotyczy dopisania albo usunięcia `attributes`.

`seen_events` mapuje identyfikator seansu na jego `businessDay` — wyłącznie po to, by dało się
przycinać stan.

**Aktualizacje stanu są zawsze scalane, nigdy nie zastępują poprzedniej zawartości.** Data, której
nie udało się pobrać, nie wnosi żadnych seansów do `pobrane_eventy` — przy semantyce „zastąp" jej
seanse wypadłyby ze stanu i wróciłyby jako fałszywe dropy przy najbliższym udanym pobraniu.

**Przycinanie** dzieje się **wewnątrz `save_state`**, nie przed jego wywołaniem: usuwane są wpisy
`seen_events` z datą wcześniejszą niż dziś oraz wpisy `drop_log` starsze niż 60 dni. Bez tego plik
rośnie bez końca.

Umieszczenie przycinania w `save_state` jest celowe. Gdy było osobnym wywołaniem w `main`, usunięcie
go przechodziło przez cały zestaw testów — nic nie pokrywało `main`. Reguła, o której trzeba
pamiętać, jest słabsza od reguły, której nie da się pominąć.

## Przepływ jednego cyklu

1. Wczytaj konfigurację i stan. Gdy jest sekcja `schedule`, a minuta nie mieści się w oknie —
   zakończ kodem 0 przed pierwszym żądaniem HTTP i bez dotknięcia pliku stanu.
2. Dla każdej **sieci** występującej w `cinemas`: `cinema_names(...)` — odśwież nazwy kin. Nazwy są
   potrzebne w treści powiadomienia, a konfiguracja trzyma wyłącznie identyfikatory. Nazwy nowe
   nadpisują stare, stare bez odpowiednika zostają, bo powiadomienie musi wyjść nawet wtedy, gdy
   ten krok zawiedzie.
3. Dla każdego kina: `fetch(...)` providera jego sieci. `None` wyklucza kino z `kina_kompletne`
   i pomija je w całym cyklu. Co robi provider w środku, zależy od sieci:
   - Cinema City: `dates/in-cinema/...` (kino nie gra codziennie, więc pytanie o kalendarzowy
     zakres generowałoby puste odpowiedzi), potem `film-events/...` na każdą graną datę —
     bezwarunkowo, bo warunkowe i tak nie działa. Throttle 200 ms między żądaniami.
   - Helios: jedna strona repertuaru, wykonanie bloba przez `qjs`, filtr dat do horyzontu.
4. `detect()` — dopasowanie do wpisów `watch` **oraz** diff. Jedno miejsce, nie dwa.
5. Wyślij grupę (film × kino) — jedną wiadomość, a gdy treść nie mieści się w limicie Telegrama,
   kolejne części, z odstępem 1,2 s. Grupa liczy się jako dostarczona dopiero, gdy wyślą się
   wszystkie części. Grupy z `notify: false` pomija się na tym kroku.
6. Zapisz stan według reguł poniżej.

Pełny cykl obu sieci to ok. 39 żądań i ok. 10 s: 37 na jedno kino Cinema City przy ok. 35 granych
dniach (ok. 650 KB po kompresji) plus 2 na Helios, bo tam jedna strona niesie cały horyzont.

## Reguły utrwalania stanu

Sedno poprawności całego narzędzia. Cel: **at-least-once** — duplikat wiadomości irytuje,
przegapiony drop kosztuje bilet.

| Sytuacja | `seen_events` |
|---|---|
| Wysyłka grupy udana | dopisz ID tej grupy |
| Wysyłka grupy nieudana | **nie dopisuj** |
| Grupa z `notify: false` | dopisz bezwarunkowo — nie ma wysyłki, która mogłaby zawieść |
| Pobranie daty nieudane (po 3 próbach) | bez zmian |
| Kino, dla którego provider zwrócił `None` | bez zmian |
| Zimny start, kino w `kina_kompletne` | dopisz wszystkie pobrane pasujące, ustaw `warm` |
| Zimny start, kino poza `kina_kompletne` | **nie dopisuj**, zostaw zimną |
| Przebieg `--dry-run` | **nie zapisuj** |

Wiersz `--dry-run` nie jest formalnością: podgląd, który po cichu ociepliłby pary, zjadłby dropa
bez wysłania powiadomienia i złamał at-least-once. Przebieg próbny nie dotyka pliku stanu w żadnej
sekcji, łącznie z flagą `warm` i z wpisami cichymi, którym nic nie mogłoby się nie udać.

Reguły są tak proste dlatego, że nie ma cache'u HTTP. Wcześniejsza wersja projektu utrwalała
`Last-Modified` i wymagała dwóch dodatkowych reguł — blokady aktualizacji przy nieudanej wysyłce
oraz usuwania wpisu przy nieudanym pobraniu — żeby data nie wpadła w martwą strefę, w której
kolejne cykle dostają `304` i nigdy nie widzą jej seansów, mimo że nie ma ich w baseline. Usunięcie
cache'u likwiduje tę klasę błędów w całości: każde pobranie jest bezwarunkowe, więc dane albo są,
albo ich nie ma.

Nieudana wysyłka nie może wywołać duplikatu, bo seanse już dopisane do `seen_events` i tak nie
zostaną uznane za nowe, ani zapętlenia — grupy wysłane skutecznie znikają ze zbioru dropów, więc
ten monotonicznie maleje aż do zbieżności.

Tabela opisuje, **co ostatecznie ląduje w pliku**, a nie gdzie zapada decyzja: `warm` i zbiór
widzianych seansów wylicza `detect()`, `main` jedynie autoryzuje zapis.

Zapis pliku jest atomowy (zapis do pliku tymczasowego i `rename`), żeby przerwany proces nie
zostawił uszkodzonego JSON-a. Na maszynie z 256 MB RAM i jednym rdzeniem przerwanie w środku zapisu
nie jest teoretyczne. Serializacja jest **deterministyczna** — `sort_keys=True`, stałe wcięcie,
końcowy znak nowej linii. Bez tego zabezpieczenie „commit tylko przy realnej zmianie", oparte na
porównaniu bajtów, reagowałoby na przypadkową kolejność kluczy wynikającą z kolejności iteracji po
konfiguracji i odpowiedziach API. Ta konkretna motywacja jest dziś historyczna (VPS nie commituje
stanu), ale determinizm zostaje — bez niego nie da się porównać dwóch stanów ani odróżnić realnej
zmiany od przetasowania kluczy.

## Zimny start

Przy pierwszym uruchomieniu każdy seans jest nowy. Bez obsługi tego przypadku pierwszy cykl
wysłałby setki wiadomości.

Zasada: **para (wpis `watch` × kino) w pierwszym cyklu tylko zapisuje stan i nie wysyła nic.**
Dotyczy to również wpisów `notify: false` — one nie wysyłają nigdy, ale baseline zapisują tak samo.

Brak klucza w `watch_state` liczy się jako para zimna, na równi z `warm: false`.

Para ociepla się, gdy jej kino znajdzie się w `kina_kompletne`, czyli gdy provider zwrócił dla niego
listę seansów zamiast `None`. Baseline tworzą wszystkie pasujące seanse, które udało się pobrać.

**Pusto spełniony warunek.** Gdy pobranie listy dat kina Cinema City zawiedzie, zbiór jego dat jest
pusty — warunek oparty na „żadna data nie zawiodła" byłby wtedy prawdziwy pusto i ocieplił parę
z zerowym baseline. Dlatego kryterium jest pozytywne: provider musi **potwierdzić skan**, a nie
jedynie nie zgłosić błędu. To ten sam powód, dla którego provider Heliosa zwraca `None`, a nie pustą
listę, gdy nie potrafi odczytać strony.

### Dlaczego nie wymagamy wszystkich dat

Naturalne wzmocnienie — „ociepl dopiero, gdy każda data zwróci treść" — tworzy pułapkę bez wyjścia.
Jedna data trwale zwracająca błąd wykluczałaby kino w **każdym** cyklu, więc wpis nigdy by się nie
ociepli i **nigdy nie wysłałby powiadomienia**. Po cichu, bez żadnego sygnału.

Dla narzędzia, którego cała racja bytu to at-least-once, trwałe milczenie jest najgorszym możliwym
wynikiem — gorszym niż fałszywy alarm. Dlatego wybieramy odwrotny kompromis:

> Data, która zawiodła podczas zimnego startu, nie trafia do baseline. Kolejne cykle pobierają ją
> normalnie, a gdy w końcu się powiedzie, jej seanse zostaną raz zgłoszone jako nowe, mimo że są
> w sprzedaży od dawna.

Cena jest ograniczona do jednego dnia repertuaru i tylko w rzadkim przypadku trwale niedostępnej
daty. W zamian **żadna para nie może pozostać zimna w nieskończoność** — wystarczy jeden udany skan
kina.

## Konfiguracja

```yaml
horizon_days: 90
cinemas: ["cc:1090", "cc:1064", "helios:warszawa/kino-helios-blue-city"]
watch:
  - match: "Backrooms"
  - match: "/^Diuna.*3$/"
    cinemas: ["cc:1090"]
    attributes: [imax]
  - match: "/.*/"
    notify: false
schedule:
  hours: [8, 22]
  before: 2
  after: 3
```

`match` to fragment nazwy — porównanie ignoruje wielkość liter i polskie znaki diakrytyczne
(`Zolw` znajdzie `Żółw`). Wartość otoczona ukośnikami jest traktowana jako wyrażenie regularne;
normalizacja diakrytyków **nie** obowiązuje w tym trybie, wzorzec działa na oryginalnym tytule
przez `re.search` (kotwice `^` i `$` piszemy jawnie, jak w przykładzie).

Opcjonalne `cinemas` zawęża wpis do podzbioru kin globalnych. Kino spoza globalnej listy jest błędem
konfiguracji, nie cichym rozszerzeniem zakresu.

Opcjonalne `attributes` wymaga, by seans miał **wszystkie** wymienione atrybuty. Wartości są
porównywane dosłownie z `Event.attribute_ids`, czyli z tym, co wpisał provider: `imax`, `4dx`,
`3d` w Cinema City, a w Heliosie nazwa sali i typ kopii małymi literami (`dream`, `2d`). Jedno pole
modelu obsługuje oba światy, więc konfiguracja nie potrzebuje osobnego pojęcia „sala" — patrz
„Rozpoznanie Heliosa".

Opcjonalne `notify: false` czyni wpis cichym — patrz następna sekcja.

Opcjonalna sekcja `schedule` ogranicza pracę do okien wokół pełnych godzin; poza oknem proces
kończy się natychmiast, bez żądania HTTP i bez dotknięcia stanu. Godziny liczone są w strefie
`Europe/Warsaw`, niezależnie od strefy maszyny, więc zmiana czasu nie przesuwa okien. Bez tej sekcji
każde uruchomienie wykonuje pełny cykl. Szczegóły i współpraca z cronem: `deploy/README.md`.

**Horyzont 90 dni**, nie 30. Przedsprzedaże premier w Cinema City otwierają się nierzadko na
terminy odleglejsze niż miesiąc — przy horyzoncie 30 dni drop zostałby wykryty dopiero, gdy data
wejdzie w okno, czyli tygodnie po starcie sprzedaży. Dłuższy horyzont jest praktycznie darmowy,
bo endpoint `dates` zwraca wyłącznie dni faktycznie grane: pytanie o 90 dni przy dwutygodniowym
repertuarze daje tyle samo żądań, co pytanie o 30. Dla Heliosa horyzont wyłącznie **przycina** to,
co niesie strona (ok. 32 dni) — wydłużanie go nic tam nie daje i nic nie kosztuje.

## Obserwacja bez powiadomienia (`notify: false`)

Wpis z `notify: false` przechodzi **całą** ścieżkę: zimny start, dopasowanie, diff — i zapisuje
`seen_events` oraz wpis w `drop_log` **bezwarunkowo**. Nie ma tu żadnego wyjątku od reguł
utrwalania, bo nie ma dostarczenia, które mogłoby zawieść: reguła „nie dopisuj po nieudanej wysyłce"
istnieje wyłącznie dlatego, że wysyłka bywa nieudana. Wpis cichy pomija tylko krok wysyłki, więc
jedyną sensowną semantyką jest zapis natychmiastowy.

Zastosowanie jest konkretne: wpis łapiący wszystko (`match: "/.*/"`, `notify: false`) obok dwóch
zwykłych wpisów. Cały repertuar obu sieci trafia wtedy do `drop_log` z `notified: false`, a na
Telegram idą tylko te dwa filmy. Bez tego pomiar godzin publikacji wymagałby albo osobnego
narzędzia, albo zalania skrzynki.

Wpisy **nakładają się** i to jest poprawne: seans obserwowanego filmu daje dwa wpisy w `drop_log`,
jeden z wpisu zwykłego i jeden z łapacza. Klucze `watch_state` są różne, więc baseline'y są
niezależne, a pole `notified` pozwala analizie rozdzielić jedno od drugiego. Odjęcie duplikatów
byłoby błędem — to dwa niezależne pomiary tego samego zdarzenia.

`--dry-run` niczego cichego nie wypisuje: podgląd pokazuje to, co poszłoby na Telegram, a z wpisu
cichego nie idzie nic.

## Argumenty wiersza poleceń

| Argument | Domyślnie | Działanie |
|---|---|---|
| `--config PATH` | `config.yaml` | ścieżka do konfiguracji |
| `--state-dir PATH` | `state/` | katalog pliku `seen.json` |
| `--dry-run` | wyłączone | wykonuje cykl, wypisuje co by wysłał, **nie zapisuje stanu** |
| `--force-send MATCH` | — | ignoruje `seen_events` dla wskazanego wpisu i wysyła jego seanse |
| `--verbose` | wyłączone | logowanie każdego żądania wraz z kodem odpowiedzi |

`--force-send` przyjmuje wartość `match` wpisu i służy wyłącznie do sprawdzenia realnej wysyłki.
Po udanej wysyłce **dopisuje** `seen_events` normalnie — inaczej każde kolejne uruchomienie
wysyłałoby to samo. Nie ociepla par zimnych i nie omija reguł utrwalania. Wartość niepasująca do
żadnego wpisu daje ostrzeżenie w logu, nie błąd — literówka nie powinna przerywać cyklu.

## Format powiadomienia

```
🎬 Backrooms. Bez wyjścia
📍 Kraków Bonarka · 6 nowych seansów

  pt 15.08  18:30  Sala 4 · IMAX     https://tickets.cinema-city.pl/api/order/1600867
  pt 15.08  21:15  Sala 4 · IMAX     https://tickets.cinema-city.pl/api/order/1600868
  sb 16.08  12:00  Sala 1            https://tickets.cinema-city.pl/api/order/1600869
  sb 16.08  15:30  Sala 1            https://tickets.cinema-city.pl/api/order/1600870
  sb 16.08  20:00  Sala 4 · IMAX     https://tickets.cinema-city.pl/api/order/1600871
  nd 17.08  17:45  Sala 2 · 4DX      https://tickets.cinema-city.pl/api/order/1600872
```

Grupa dłuższa niż jedna wiadomość dzieli się na części, a nagłówek dostaje wtedy licznik
`🎬 Backrooms. Bez wyjścia  (2/3)`. Każda część powtarza nagłówek, więc czyta się ją samodzielnie.

Jedna grupa na parę (film × kino). Przy premierze wchodzącej z czterdziestoma seansami naraz
grupowanie jest różnicą między jednym powiadomieniem a czterdziestoma.

Ustalenia formatu:

- **Link jest per seans**, bo `bookingLink` to pole eventu — jeden link na grupę wskazywałby
  losowy seans.
- **Bez ucinania listy** — ukryte seanse to dokładnie ta informacja, po którą sięga czytelnik.
  Telegram odrzuca wiadomości dłuższe niż 4096 znaków, więc grupa dzieli się na części po
  3500 znaków; zapas pokrywa polskie znaki wielobajtowe i przyszły wzrost nagłówka. Pojedynczy
  wiersz nigdy nie pęka między wiadomościami, a licznik w nagłówku podaje sumę dla całej grupy,
  nie dla części.
- **Odstęp 1,2 s między częściami.** Telegram przyjmuje mniej więcej jedną wiadomość na sekundę do
  jednego czatu. Bez odstępu duża grupa dostaje `429`, kod czyta to jako nieudaną wysyłkę i wysyła
  całą grupę od nowa — przy dostatecznie dużym dropie w każdym kolejnym cyklu, bez końca. Odstęp
  jest tańszy niż obsługa `429` w notyfikatorze.
- **Etykiety formatów** pochodzą z `attribute_ids`. Identyfikatory są w API Cinema City pisane
  małymi literami z myślnikami, więc potrzebna jest jawna mapa slug → etykieta; wszystko spoza mapy
  pomijamy jako szum:

  | slug | etykieta |
  |---|---|
  | `imax` | IMAX |
  | `4dx` | 4DX |
  | `screenx` | ScreenX |
  | `dolby-cinema` | Dolby Cinema |
  | `vip` | VIP |
  | `3d` | 3D |

  Mapa jest świadomie tylko dla Cinema City. Atrybuty Heliosa (`dream`, `2d`) w niej nie występują,
  więc nie stają się etykietą — ale nazwa sali ląduje tam w `auditorium`, więc wiersz i tak pokazuje
  `Dream`. Innymi słowy: to samo pole modelu, dwie różne drogi na ekran, zero martwego kodu.
- **Odmiana liczebnika** w nagłówku według reguł polskich: `1 nowy seans`, `2–4 nowe seanse`,
  `5+ nowych seansów`, z wyjątkiem końcówek 12–14, które biorą formę dopełniaczową.
- **Nazwa kina** pochodzi z `cinema_names`. Gdy krok 2 przepływu zawiedzie i wpisu brakuje,
  pokazujemy sam identyfikator kina, z prefiksem sieci. Powiadomienie musi wyjść nawet bez ładnej
  nazwy.
- **Strefa Europe/Warsaw wyłącznie przy liczeniu `dziś + horizon_days`.** Maszyna bywa ustawiona
  na UTC (runner GHA zawsze był), więc bez jawnej strefy skan blisko północy obejmowałby zły zakres
  dat. Godzin seansów **nie konwertujemy** — `eventDateTime` z API jest już czasem lokalnym kina,
  więc nałożenie na nie strefy przesunęłoby każdy seans.
- Skróty dni tygodnia z własnej mapy, nie z `locale` — locale bywa niedostępne w kontenerze,
  a w obrazie Alpine tym bardziej.

## Uruchamianie

Stan na dziś: **cron na VPS-ie**. GitHub Actions był etapem pierwszym i jest już **historią** —
workflow `check` jest celowo wyłączony (`DISABLED_MANUALLY`). Poniżej najpierw powód tej migracji,
bo to jedyny pomiar, który naprawdę rozstrzygnął sprawę, a potem stan bieżący.

### Etap pierwszy: GitHub Actions (historyczny)

Repozytorium **publiczne** na koncie `Laaidback`. Widoczność ma tu wymiar finansowy:

| Widoczność | Limit | Koszt crona co 5 min |
|---|---|---|
| publiczne | brak limitu minut | 0 zł |
| prywatne | 2000 min/mies | ~8640 min/mies → ok. 53 USD/mies |

GHA nalicza minimum jedną minutę na zadanie, a 8640 uruchomień miesięcznie przy prywatnym repo
przekracza darmowy limit ponad czterokrotnie. Repo publiczne ujawnia wyłącznie tytuły
obserwowanych filmów i numery kin. Token bota i identyfikator czatu trafiały do **GitHub Secrets**,
bezpiecznych również w repozytorium publicznym.

Założenie, które się nie utrzymało: „cron GHA bywa opóźniany o kilkanaście minut, a seanse są
dostępne godzinami, więc to akceptowalne".

**Pomiar wykazał coś innego.** Wpisane `*/5` (288 uruchomień na dobę) było realnie dostarczane
jako **ok. jedno uruchomienie na dwie godziny**, a najgorsza zaobserwowana przerwa wyniosła
**sześć godzin**. Nadmiar kolejkował się i był anulowany przez `concurrency`, co dodatkowo
generowało maile o rzekomych porażkach. Dlatego cron w workflow zjechał później do `*/15` — ta sama
realna częstotliwość, mniej szumu.

Sześciogodzinna dziura to dokładnie ten tryb awarii, którego całe narzędzie ma nie mieć: drop
wykryty pół dnia po publikacji jest wart tyle, co brak powiadomienia. To był powód przenosin na
VPS, nie oszczędność ani wygoda.

**Stan** trafia na dedykowaną gałąź `state`. Gałąź `main` zostaje czysta. Odrzucone alternatywy:
`actions/cache` bywa eksmitowany i znika po siedmiu dniach bez użycia, co oznaczałoby zimny start
i przegapiony drop; commitowanie na `main` zamieniłoby historię w śmietnik.

Trzy zabezpieczenia wokół gałęzi `state`:

- `concurrency: { group: ccdrop, cancel-in-progress: false }` — opóźnienia crona przy interwale
  pięciominutowym powodują nakładanie się uruchomień, a dwa równoległe pushe na tę samą gałąź
  kończą się odrzuceniem non-fast-forward albo nadpisaniem stanu.
- Push z ponowieniem przez `fetch` + `reset --hard origin/state` + ponowne zastosowanie zapisu
  stanu. **Nie** `pull --rebase` — konflikt na tym samym pliku JSON nie scali się automatycznie,
  tylko przerwie rebase, a ponowienie już nie pomoże. Nigdy `--force`.
- **Commit tylko wtedy, gdy stan faktycznie się zmienił.** W typowym cyklu nic się nie zmienia,
  więc bez tego warunku gałąź dostałaby 8640 pustych commitów miesięcznie.

Workflow wymaga `permissions: { contents: write }` dla `GITHUB_TOKEN` oraz checkoutu gałęzi
`state` — bez tego pierwszy `workflow_dispatch` rozbije się na pushu.

Uwaga o cronie: GitHub wyłącza zaplanowane workflowy w publicznym repozytorium po 60 dniach bez
aktywności. Commity ze zmianami stanu i przycinaniem tę aktywność generują, więc w praktyce problem
nie wystąpi — ale gdyby detektor przez dwa miesiące nie znalazł nic, wymaga ręcznego wznowienia.

Cała ta maszyneria wokół gałęzi `state` nadal jest w `.github/workflows/check.yml`, bo workflow
zostaje w repozytorium jako droga awaryjna. **Nie wolno go włączyć przy działającym VPS-ie**:
dwie instancje mają osobne pliki stanu, więc każda wykryje ten sam drop niezależnie i każda wyśle
powiadomienie — wszystko przyjdzie podwójnie. Sekcja `schedule` tego nie ratuje, bo repozytorium
ma własny `config.yaml` i tak czy inaczej cron czasem trafiłby w okno.

### Etap drugi: VPS (stan bieżący)

Ten sam kod Pythona, **zero zmian**, uruchamiany z crona na mikr.usie: Alpine Linux, busybox
`crond`, bez systemd, bez roota, bez Dockera. Stan nie idzie już do gita — leży w katalogu
domowym. Instalacja, crontab, sekrety, weryfikacja i tryby pracy: **`deploy/README.md`**.

Dwie rzeczy z tego wdrożenia mają znaczenie projektowe, nie tylko operacyjne:

- **Konfiguracja produkcyjna musi leżeć poza klonem repozytorium.** `config.yaml` jest plikiem
  śledzonym, więc edytowanie go w miejscu sprawiło, że pierwszy `git pull` przerwał się konfliktem
  scalania. Stąd `--config ~/.config/ccdrop/config.yaml`.
- **`qjs` jest twardą zależnością runtime'u** dla sieci Helios, jedyną instalowaną z roota. Bez niej
  Helios nie zwraca nic, a awaria jest cicha dla użytkownika.

Dockerfile nigdy nie powstał i nie jest potrzebny: 256 MB RAM nie zaprasza do dodatkowej warstwy,
a `python3` i `git` są w obrazie.

#### Tryb bieżący jest tymczasowy

Detektor chodzi **co minutę, całą dobę**, z wpisem `notify: false` łapiącym cały repertuar.
Nie jest to stan docelowy, a **pomiar**: chcemy wiedzieć, o których godzinach kina publikują nowe
seanse, zanim zawęzimy odpytywanie do okna. Zgadywanie przy tym wyborze kosztuje albo przegapione
dropy, albo ruch bez pokrycia.

| Tryb | Cron | `schedule` | Żądania na dobę |
|---|---|---|---|
| pomiar (obecny) | `* * * * *` | brak | ok. 56 000 |
| okno (docelowy) | `58,59,0,1,2,3 * * * *` | `[8, 22]`, `before: 2`, `after: 3` | ok. 3 500 |

Szesnastokrotna różnica w ruchu jest jedynym powodem, żeby z pomiaru wyjść. Kiedy `drop_log` zbierze
dość materiału (`tools/drop_hours.py` liczy udział wykryć w oknie 58–03 wokół pełnej godziny),
przełączenie to dopisanie sekcji `schedule` i zmiana minut w crontabie — bez zmiany kodu i bez
utraty ciepła par.

## Izolacja od konta firmowego

Maszyna ma skonfigurowaną wyłącznie tożsamość firmową i wsiąknęłaby ona w nowy projekt
automatycznie:

```
user.email      = swietojanski.krystian@greenhive.team
commit.gpgsign  = true
gpg.format      = ssh
user.signingkey = ~/.ssh/id_ed25519.pub
```

Każdy commit jest domyślnie podpisywany firmowym kluczem SSH i opatrzony firmowym adresem. Nowy
projekt wymaga czterech ustawień, wszystkich **lokalnych** dla repozytorium:

| Obszar | Ustawienie |
|---|---|
| Autor | `user.name` oraz `user.email` = `24231775+Laaidback@users.noreply.github.com` |
| Podpis | `commit.gpgsign=false` |
| Klucz | nowy `id_ed25519_personal` + `Host github-personal` w `~/.ssh/config` |
| Remote | `git@github-personal:Laaidback/cinema-city-drop-detector.git` |

Osobny klucz jest konieczny, nie kosmetyczny: GitHub nie pozwala wpiąć tego samego klucza SSH do
dwóch kont, a obecny klucz jest już powiązany z kontem firmowym.

Konto prywatne: **Laaidback**, ID `24231775` — potwierdzone przez publiczne API GitHuba. Adres
noreply zamiast prywatnej skrzynki, bo w repozytorium publicznym adres autora commita jest jawny.

## Sekrety

| Nazwa | Skąd | Gdzie |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | @BotFather, `/newbot` | VPS `~/.config/ccdrop/env` (600), lokalnie `.env` |
| `TELEGRAM_CHAT_ID` | `tools/get_chat_id.py` | VPS `~/.config/ccdrop/env` (600), lokalnie `.env` |

Oba trafiały wcześniej do **GitHub Secrets**, bo tam czytał je workflow. Przy wyłączonym workflow
nie są używane — jeśli kiedyś wróci, trzeba je tam odtworzyć.

Detektor czyta je wyłącznie ze środowiska procesu; nie ma ładowania `.env` w kodzie. `.env`
jest w `.gitignore`. Warunek działania `get_chat_id.py`: trzeba najpierw napisać cokolwiek do
swojego bota, inaczej nie ma on prawa odpisać i `getUpdates` zwróci pustkę.

## Testy

Wszystkie offline, bez sieci, bez prawdziwego Telegrama i bez uruchamiania `qjs`. Fixture'y to
zapisana odpowiedź JSON z produkcyjnego API Cinema City, zapisana strona Heliosa i wyciągnięty
z niej stan repertuaru.

`detector` — rdzeń:

- zimny start nie wysyła powiadomień,
- nowy seans dla obserwowanego filmu jest wykrywany,
- brak zmian nie generuje dropa,
- seans zniknięty i przywrócony nie wysyła się drugi raz,
- seans nieobserwowanego filmu jest ignorowany,
- dopasowanie po nazwie ignoruje wielkość liter i diakrytyki,
- dopasowanie po wyrażeniu regularnym działa na oryginalnym tytule,
- zawężenie wpisu do podzbioru kin,
- zawężenie wpisu do atrybutów (`attributes`) i osobny klucz stanu dla takiego wpisu,
- dopisanie kina do globalnej listy wywołuje zimny start tylko dla nowej pary,
- kino, dla którego provider zwrócił `None`, nie ociepla żadnej ze swoich par,
- brak klucza w `watch_state` jest traktowany jak para zimna,
- `force_match` raportuje seans obecny już w `seen_events`.

`main` — reguły utrwalania, najbardziej podatne na błąd:

- nieudana wysyłka nie dopisuje `seen_events`,
- powtórzony cykl po nieudanej wysyłce dostarcza tego samego dropa,
- awaria skanu kina zostawia wszystkie jego pary zimne,
- para z jedną trwale błędną datą **ociepla się mimo to**,
- istniejące `seen_events` przeżywają dopisanie nowego dropa,
- `--dry-run` nie modyfikuje pliku stanu w żadnej sekcji,
- wpis cichy nie wysyła nic, a mimo to zapisuje `seen_events` i `drop_log` z `notified: false`,
- nieudana wysyłka wpisu powiadamiającego nie blokuje zapisu wpisu cichego z tego samego cyklu,
- nieudana część wielocząstkowej wiadomości nie zapisuje niczego i nie wysyła części dalszych.

Każda z tych reguł musi być zweryfikowana **mutacyjnie** — zepsuj odpowiadającą jej linię i sprawdź,
czy któryś test faktycznie się czerwieni. W tym projekcie trzykrotnie trafił się test, który
wyglądał na pokrycie, a nie mógł zawieść.

**Pułapka: nieświeży bajtkod.** Przebieg mutacyjny musi usuwać `__pycache__` i ustawiać
`PYTHONDONTWRITEBYTECODE=1`. CPython unieważnia `.pyc` po parze **(mtime, rozmiar)** pliku
źródłowego, a mtime ma rozdzielczość jednej sekundy. Mutacja niezmieniająca rozmiaru (np. `>=` na
`>`, `and` na `or`) zapisana w tej samej sekundzie co poprzedni odczyt jest dla interpretera
niewidoczna: pytest uruchamia **kod niezmutowany**, wszystko jest zielone i mutacja wygląda na
przeżytą. Zdarzyło się to w tym projekcie i kosztowało pół godziny szukania błędu w testach, których
tam nie było.

`api` — parsowanie fixture'a, backoff po `429`, poddanie się po trzech próbach, throttle między
żądaniami. (Ponowienie po `5xx` i po wyjątku sieciowym kod obsługuje, ale osobnego testu na to
nie ma — luka do zamknięcia.)

`providers` — rejestr zawiera obie sieci i buduje z niego działający provider; prefiks jest
zdejmowany przed żądaniem i nakładany na zwracane dane.

`helios` — parsowanie stanu strony: klucz grupy z `_id` (w tym postaci `e<id>`), fallback na
`m<id>`, atrybuty z `cinemaScreen.feature` i `moviePrint.printType`, filtr horyzontu, i pełny zestaw
przypadków, w których provider zwraca `None` (błąd HTTP, brak bloba, błąd `qjs`, timeout, brak
binarki, nieparsowalne wyjście, nieznany kształt danych). Klient i `qjs` są zaślepione, więc testy
nie potrzebują ani sieci, ani QuickJS-a.

`config` — normalizacja prefiksu sieci, odrzucenie nieznanej sieci, kino spoza globalnej listy,
`attributes`, `notify`, walidacja `schedule` (dwie godziny 0–23, kolejność, nieujemne marginesy,
suma < 59).

`schedule` — granice okna po minucie i po godzinie, przeliczanie strefy.

`notifier` — grupowanie po (film × kino), **podział długiej grupy na części** (nigdy ucinanie:
osobny test pilnuje, że żadna część nie ogłasza ukrytych seansów), licznik części liczony dla całej
grupy, mapa slug → etykieta, odmiana liczebnika, formatowanie daty.

`state` — cykl zapis/odczyt, przycinanie minionych dat, zachowanie przy uszkodzonym pliku,
scalanie zamiast zastępowania, deterministyczna serializacja (ten sam stan zapisany dwukrotnie
daje identyczne bajty niezależnie od kolejności wstawiania kluczy).

## Weryfikacja end-to-end

1. `pytest` — komplet testów zielony.
2. Uruchomienie lokalne z `--dry-run`: cykl się wykonuje, nic nie wysyła, wypisuje co by wysłał.
3. Wpis `watch` pasujący do filmu **już** granego: pierwszy cykl milczy (zimny start), drugi też
   (brak zmian).
4. Test realnej wysyłki flagą `--force-send`, która pomija sprawdzenie `seen_events` dla jednego
   wpisu. Wyczyszczenie stanu **nie** nadaje się do tego testu — zrobiłoby z wpisu wpis nowy, więc
   cykl z definicji by zamilkł.
5. Symulacja awarii: zły token Telegrama, cykl kończy się błędem wysyłki. Weryfikacja, że
   `seen_events` nie drgnęły i że kolejny poprawny cykl dostarcza dropa.
6. Na VPS-ie: `crontab -l`, potem log przez kilka minut — kolejne cykle z linią
   `Pobrano N seansów`. Zero ostrzeżeń z prefiksem `Helios:` znaczy, że `qjs` działa. Procedura
   w `deploy/README.md`. *(Wcześniej tym krokiem był `workflow_dispatch` w GitHub Actions
   z commitem na gałąź `state`; workflow jest wyłączony, więc krok jest historyczny.)*
7. Obserwacja przez dobę: brak fałszywych powiadomień przy niezmienionym repertuarze.
8. **Po dobie działania dopisanie drugiego wpisu `watch`** dla filmu już granego w tym samym kinie.
   Oczekiwane: cykl milczy (zimny start nowej pary), a kolejna zmiana repertuaru nie wywołuje lawiny
   starych seansów.
9. Dla drugiej sieci osobno: kino Heliosa w `cinemas`, wpis z `attributes: [dream]`. Oczekiwane:
   pierwszy cykl zapisuje baseline i milczy, a `qjs` usunięty z systemu daje ostrzeżenie w logu
   i **zimną** parę, nie pustą.

## Kwestie rozstrzygnięte po wdrożeniu

- Token bota Telegram — wygenerowany w @BotFather, trzymany w `~/.config/ccdrop/env` (600) na VPS-ie
  i w lokalnym `.env`. Nigdy nie przechodzi przez historię rozmowy ani przez repozytorium.
- Zawartość konfiguracji — lista filmów i identyfikatory kin, uzupełniona przez
  `tools/list_cinemas.py` i `tools/list_helios_cinemas.py`. Konfiguracja produkcyjna leży **poza
  klonem**, w `~/.config/ccdrop/config.yaml`; `config.yaml` w repozytorium jest tylko przykładem.

## Otwarte kwestie

- Kiedy wyjść z trybu pomiarowego. Decyzję podejmie rozkład z `tools/drop_hours.py`; do tego czasu
  detektor chodzi co minutę i loguje cały repertuar jako obserwacje ciche.
- Wydarzenia specjalne Heliosa nie dostają atrybutu formatu (`moviePrint` pod `screeningMovies[]`).
  Do naprawy dopiero wtedy, gdy ktoś będzie chciał zawężać wpis po formacie właśnie dla nich.
- Brak testu ponowienia po `5xx` i po wyjątku sieciowym w kliencie Cinema City.
