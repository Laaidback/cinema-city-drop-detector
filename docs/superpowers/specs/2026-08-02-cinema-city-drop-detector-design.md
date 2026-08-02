# Cinema City drop detector — projekt

Data: 2026-08-02
Status: zaakceptowany po recenzji, gotowy do planu implementacji

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
- konfiguracja w pliku, edytowana ręcznie.

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
   Cinema City.
3. **`If-Modified-Since` działa.** Przy niezmienionym repertuarze odpowiedź to `304` i **0 bajtów**
   zamiast ~101 KB. Dzięki temu koszt cyklu jest niemal niezależny od liczby skanowanych dni.

Konsekwencja dla dopasowywania filmów: film przed premierą **nie istnieje jeszcze** w API, więc nie
ma `filmId`. Obserwowane pozycje są dopasowywane wyłącznie **po nazwie**.

## Architektura

Rdzeniem jest czysta funkcja `detect()`. Kluczowe: operuje **wyłącznie** na zbiorze widzianych
seansów, nie na całym pliku stanu. Nagłówki `Last-Modified` to domena warstwy HTTP i nigdy nie
przechodzą przez rdzeń.

```
detect(config, seen, pobrane_eventy, kina_kompletne) -> (dropy, aktualizacje_seen)
```

`kina_kompletne` to zbiór **numerów kin**, dla których w tym cyklu udało się pobrać listę dat.
Tylko takie kino może ocieplić swoją parę przy zimnym starcie. Jednostką jest kino, nie pojedyncza
data, bo baseline wpisu obejmuje cały jego repertuar w danym kinie.

Celowo **nie** wymagamy, by wszystkie daty kina pobrały się bezbłędnie — powód i cena tego wyboru
w sekcji „Zimny start".

Ustawienie flagi `warm` należy do `detect()`, tak samo jak dopasowywanie. `main` decyduje wyłącznie,
czy zwrócone aktualizacje wolno utrwalić.

Bez I/O, bez sieci, bez Telegrama. Cała logika „co jest nowe" jest testowalna bez wychodzenia poza
proces.

```
cinema-city-drop-detector/
├─ config.yaml              # co śledzić — jedyny plik edytowany na co dzień
├─ ccdrop/
│  ├─ config.py             # wczytanie i walidacja konfiguracji
│  ├─ api.py                # klient HTTP: warunkowe GET-y, throttle, backoff
│  ├─ models.py             # dataclasses: Cinema, Film, Event, Drop
│  ├─ detector.py           # czysta logika diffowania
│  ├─ notifier.py           # formatowanie wiadomości i wysyłka
│  ├─ state.py              # odczyt, zapis, przycinanie stanu
│  └─ main.py               # spięcie powyższych, reguły zapisu stanu
├─ tools/
│  ├─ get_chat_id.py        # wypisuje TELEGRAM_CHAT_ID z getUpdates
│  └─ list_cinemas.py       # wypisuje numery i nazwy kin do config.yaml
├─ tests/
└─ .github/workflows/check.yml
```

Granice: `detector` nie wie nic o HTTP ani o Telegramie, `api` nie wie nic o obserwowanych filmach,
`notifier` dostaje gotową listę dropów i tylko ją formatuje. Decyzje o tym, **co wolno utrwalić**,
podejmuje wyłącznie `main`.

## Model stanu

Plik `state/seen.json`, trzy niezależne sekcje:

```json
{
  "version": 1,
  "watch_state": {
    "Backrooms|1090": {
      "warm": true,
      "seen_events": { "1600867": "2026-08-15" }
    }
  },
  "http_cache": { "1090|2026-08-02": "Sat, 01 Aug 2026 21:07:38 GMT" },
  "cinema_names": { "1090": "Kraków Bonarka" }
}
```

**Kluczem `watch_state` jest para (wartość `match` × numer kina).** Nie sam wpis `watch` — bo
dopisanie kina do globalnej listy `cinemas` nie tworzy nowego wpisu, a para (film × nowe kino) jest
w całości nieznana i bez tego klucza zalałaby skrzynkę całym bieżącym repertuarem tego kina.

Zmiana tekstu w `match` tworzy nowy klucz, czyli świadomie wywołuje zimny start. Jest to zachowanie
pożądane: inny `match` to inne zapytanie.

`seen_events` mapuje identyfikator seansu na jego `businessDay` — wyłącznie po to, by dało się
przycinać stan.

**Aktualizacje stanu są zawsze scalane, nigdy nie zastępują poprzedniej zawartości.** Pary
zwracające `304` nie trafiają do `pobrane_eventy`, więc przy semantyce „zastąp" ich seanse
wypadłyby ze stanu i wróciłyby jako fałszywe dropy przy najbliższym `200`.

**Przycinanie** przy każdym zapisie: usuwane są wpisy `seen_events` z datą wcześniejszą niż dziś
oraz klucze `http_cache` dla minionych dat. Bez tego plik rośnie bez końca.

## Przepływ jednego cyklu

1. Wczytaj konfigurację i stan.
2. `cinemas/with-event/until/{dziś + horizon_days}` — odśwież `cinema_names`.
   Nazwy są potrzebne w treści powiadomienia, a konfiguracja trzyma wyłącznie numery.
3. Dla każdego kina: `dates/in-cinema/{id}/until/{dziś + horizon_days}` — realna lista dat.
   Kino nie gra codziennie, więc odpytywanie o kalendarzowy zakres generowałoby puste odpowiedzi.
   Niepowodzenie tego kroku wyklucza kino z `kina_kompletne` i pomija je w całym cyklu.
4. Dla każdej pary (kino, data): `film-events/...` z nagłówkiem `If-Modified-Since`, o ile para ma
   wpis w `http_cache` — bez wpisu żądanie jest bezwarunkowe.
   `304` — pomijamy, `200` — parsujemy. Throttle 200 ms między żądaniami.
   **Wyjątek:** jeżeli którakolwiek para (wpis `watch` × to kino) jest zimna, wszystkie daty tego
   kina pobieramy **bezwarunkowo**, bez `If-Modified-Since`. Uzasadnienie w sekcji „Zimny start".
5. `detect()` — dopasowanie do wpisów `watch` **oraz** diff. Jedno miejsce, nie dwa.
6. Wyślij jedną wiadomość na grupę (film × kino).
7. Zapisz stan według reguł poniżej.

Przy dwóch kinach i ~30 granych dniach to ok. 63 żądania na cykl, z czego niemal wszystkie kończą
się `304` o zerowej wielkości.

## Reguły utrwalania stanu

Sedno poprawności całego narzędzia. Cel: **at-least-once** — duplikat wiadomości irytuje,
przegapiony drop kosztuje bilet.

| Sytuacja | `seen_events` | `http_cache` |
|---|---|---|
| Wysyłka grupy udana | dopisz ID tej grupy | patrz niżej |
| Wysyłka grupy nieudana | **nie dopisuj** | **nie aktualizuj** |
| Pobranie pary nieudane (po 3 próbach) | bez zmian | **usuń wpis** |
| Zimny start, kino w `kina_kompletne` | dopisz wszystkie pobrane pasujące, ustaw `warm` | aktualizuj |
| Zimny start, kino bez listy dat | **nie dopisuj**, zostaw zimną | **nie aktualizuj** |
| Przebieg `--dry-run` | **nie zapisuj** | **nie zapisuj** |

Wiersz `--dry-run` nie jest formalnością: podgląd, który po cichu ociepliłby pary, zjadłby dropa
bez wysłania powiadomienia i złamał at-least-once. Przebieg próbny nie dotyka pliku stanu w żadnej
sekcji, łącznie z flagą `warm`.

Reguła nadrzędna dla `http_cache`, celowo konserwatywna:

> Jeżeli w cyklu **jakakolwiek** wysyłka zawiodła, nie aktualizujemy `http_cache` **w ogóle**.

Zapisanie `Last-Modified` przy jednoczesnym niezapisaniu widzianych seansów jest jedynym sposobem
na trwałe zgubienie dropa: następny cykl dostałby `304`, pominął parę i nigdy nie wysłał
powiadomienia. Reguła nie może wywołać duplikatu, bo seanse już dopisane do `seen_events` i tak
nie zostaną uznane za nowe, ani zapętlenia — grupy wysłane skutecznie znikają ze zbioru dropów,
więc ten monotonicznie maleje aż do zbieżności.

Wiersz 3 mówi **usuń**, nie „zostaw poprzednią wartość", i to rozróżnienie jest krytyczne.
Zachowanie nieaktualnego `Last-Modified` dla daty, której nie udało się pobrać, wpycha ją w martwą
strefę: kolejny cykl wyśle warunkowy GET, dostanie `304` i nigdy nie zobaczy jej seansów, mimo że
nie ma ich w baseline. Wisiałyby tam do przypadkowej zmiany nagłówka, a wtedy poleciałby komplet
seansów z całego dnia. Usunięcie wpisu kosztuje jedną pełną odpowiedź w cyklu odzyskania.

Tabela opisuje, **co ostatecznie ląduje w pliku**, a nie gdzie zapada decyzja: `warm` i zbiór
widzianych seansów wylicza `detect()`, `main` jedynie autoryzuje zapis.

Kosztem jest transfer, i to nie jednorazowy: blokada trwa **do pierwszej udanej wysyłki**. Przy
dłuższej niedostępności Telegrama każdy cykl pobiera komplet pełnych odpowiedzi zamiast `304`,
czyli ok. 6 MB co pięć minut. Świadomie tego nie ograniczamy. Rozważane odcięcie po N nieudanych
cyklach wymagałoby licznika utrwalanego wbrew całej powyższej dyscyplinie zapisu, zerowania go po
sukcesie oraz osobnej sondy sprawdzającej, czy Telegram wrócił — trzy nowe mechanizmy po to, by
zaoszczędzić transfer, który i tak obsługuje brzeg Cloudflare, a nie serwery Cinema City. Awarie
Telegrama są rzadkie i krótkie, a stan pozostaje nietknięty, więc żaden drop nie ginie. Mechanizm
sam się leczy przy pierwszej udanej wysyłce.

Zapis pliku jest atomowy (zapis do pliku tymczasowego i `rename`), żeby przerwany proces nie
zostawił uszkodzonego JSON-a. Serializacja jest **deterministyczna** — `sort_keys=True`, stałe
wcięcie, końcowy znak nowej linii. Bez tego zabezpieczenie „commit tylko przy realnej zmianie",
oparte na porównaniu bajtów, reagowałoby na przypadkową kolejność kluczy wynikającą z kolejności
iteracji po konfiguracji i odpowiedziach API.

## Zimny start

Przy pierwszym uruchomieniu każdy seans jest nowy. Bez obsługi tego przypadku pierwszy cykl
wysłałby setki wiadomości.

Zasada: **para (wpis `watch` × kino) w pierwszym cyklu tylko zapisuje stan i nie wysyła nic.**

Brak klucza w `watch_state` liczy się jako para zimna, na równi z `warm: false` — to pierwszy
warunek do zakodowania w kroku 4.

Para ociepla się, gdy jej kino znajdzie się w `kina_kompletne`, czyli gdy **lista dat** pobrała się
poprawnie. Baseline tworzą wszystkie pasujące seanse z dat, które udało się pobrać.

**Współdzielony cache.** `http_cache` jest wspólny dla wszystkich wpisów, bo kluczem jest
(kino, data). Gdy kino jest już skanowane dla innego wpisu, cache ma komplet nagłówków, więc skan
nowej zimnej pary zwróciłby same `304` — zero danych, zero błędów, a mimo to baseline pusty. Przy najbliższej zmianie repertuaru dowolnego dnia wszystkie pasujące seanse,
sprzedawane od tygodni, poleciałyby jako świeże. Dlatego obecność choćby jednej zimnej pary wymusza
bezwarunkowe pobranie wszystkich dat tego kina (krok 4 przepływu).

Pierwsze w życiu uruchomienie tej pułapki nie ujawni — przy pustym `http_cache` wszystko i tak
wraca jako `200`. Problem wychodzi dopiero przy dodaniu drugiego wpisu.

**Pusto spełniony warunek.** Gdy pobranie listy dat dla kina zawiedzie, zbiór jego par (kino, data)
jest pusty — warunek oparty na „żadna data nie zawiodła" byłby wtedy prawdziwy pusto i ocieplił parę
z zerowym baseline. Dlatego kryterium jest pozytywne: kino musi mieć **pobraną listę dat**, a nie
jedynie brak błędów.

### Dlaczego nie wymagamy wszystkich dat

Naturalne wzmocnienie — „ociepl dopiero, gdy każda data zwróci treść" — tworzy pułapkę bez wyjścia.
Jedna data trwale zwracająca błąd wyklucza kino w **każdym** cyklu: para zostaje zimna, zimna para
wymusza pobranie bezwarunkowe, więc kolejny cykl ściąga komplet dat od nowa i znów nie osiąga
kompletności. Wpis nigdy się nie ociepla, więc **nigdy nie wysyła powiadomienia**, a każdy cykl
ściąga kilka megabajtów. Wszystko po cichu.

Dla narzędzia, którego cała racja bytu to at-least-once, trwałe milczenie jest najgorszym możliwym
wynikiem — gorszym niż fałszywy alarm. Dlatego wybieramy odwrotny kompromis:

> Data, która zawiodła podczas zimnego startu, nie trafia do baseline. Jej wpis w `http_cache`
> zostaje **usunięty** (wiersz 3 tabeli), więc kolejne cykle pobierają ją bezwarunkowo. Gdy w końcu
> się powiedzie, jej seanse zostaną raz zgłoszone jako nowe, mimo że są w sprzedaży od dawna.

Usunięcie wpisu jest tu warunkiem koniecznym, nie szczegółem. Gdyby wiersz 3 zostawiał poprzednią
wartość, przesłanka „pobierane bezwarunkowo" byłaby prawdziwa wyłącznie przy pierwszym w życiu
uruchomieniu — w kinie skanowanym od miesięcy data miałaby stary nagłówek i wpadła w martwą strefę
opisaną wyżej.

Cena jest ograniczona do jednego dnia repertuaru i tylko w rzadkim przypadku trwale niedostępnej
daty. W zamian **żadna para nie może pozostać zimna w nieskończoność** — wystarczy, że pobierze się
lista dat.

## Konfiguracja

```yaml
horizon_days: 90
cinemas: [1090, 1064]
watch:
  - match: "Backrooms"
  - match: "/^Diuna.*3$/"
    cinemas: [1090]
```

`match` to fragment nazwy — porównanie ignoruje wielkość liter i polskie znaki diakrytyczne
(`Zolw` znajdzie `Żółw`). Wartość otoczona ukośnikami jest traktowana jako wyrażenie regularne;
normalizacja diakrytyków **nie** obowiązuje w tym trybie, wzorzec działa na oryginalnym tytule
przez `re.search` (kotwice `^` i `$` piszemy jawnie, jak w przykładzie).

Opcjonalne `cinemas` zawęża wpis do podzbioru kin globalnych.

**Horyzont 90 dni**, nie 30. Przedsprzedaże premier w Cinema City otwierają się nierzadko na
terminy odleglejsze niż miesiąc — przy horyzoncie 30 dni drop zostałby wykryty dopiero, gdy data
wejdzie w okno, czyli tygodnie po starcie sprzedaży. Dłuższy horyzont jest praktycznie darmowy,
bo endpoint `dates` zwraca wyłącznie dni faktycznie grane: pytanie o 90 dni przy dwutygodniowym
repertuarze daje tyle samo żądań, co pytanie o 30.

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
wysyłałoby to samo. Nie ocieplarza par zimnych i nie omija reguł utrwalania.

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

Po przekroczeniu limitu ostatni wiersz przyjmuje postać `…i 12 więcej`.

Jedna wiadomość na parę (film × kino). Przy premierze wchodzącej z czterdziestoma seansami naraz
grupowanie jest różnicą między jednym powiadomieniem a czterdziestoma.

Ustalenia formatu:

- **Link jest per seans**, bo `bookingLink` to pole eventu — jeden link na grupę wskazywałby
  losowy seans.
- **Maksymalnie 15 pozycji** na wiadomość, potem wiersz `…i N więcej`. Telegram tnie wiadomości
  po 4096 znakach.
- **Etykiety formatów** pochodzą z `attributeIds`. Identyfikatory są w API pisane małymi literami
  z myślnikami, więc potrzebna jest jawna mapa slug → etykieta; wszystko spoza mapy pomijamy jako
  szum:

  | slug | etykieta |
  |---|---|
  | `imax` | IMAX |
  | `4dx` | 4DX |
  | `screenx` | ScreenX |
  | `dolby-cinema` | Dolby Cinema |
  | `vip` | VIP |
  | `3d` | 3D |

- **Odmiana liczebnika** w nagłówku według reguł polskich: `1 nowy seans`, `2–4 nowe seanse`,
  `5+ nowych seansów`, z wyjątkiem końcówek 12–14, które biorą formę dopełniaczową.
- **Nazwa kina** pochodzi z `cinema_names`. Gdy krok 2 przepływu zawiedzie i wpisu brakuje,
  pokazujemy sam numer kina. Powiadomienie musi wyjść nawet bez ładnej nazwy.
- **Strefa Europe/Warsaw wyłącznie przy liczeniu `dziś + horizon_days`.** Runner GitHub Actions
  chodzi w UTC, więc bez jawnej strefy skan blisko północy obejmowałby zły zakres dat.
  Godzin seansów **nie konwertujemy** — `eventDateTime` z API jest już czasem lokalnym kina,
  więc nałożenie na nie strefy przesunęłoby każdy seans.
- Skróty dni tygodnia z własnej mapy, nie z `locale` — locale bywa niedostępne w kontenerze CI.

## Uruchamianie

### Etap pierwszy: GitHub Actions

Repozytorium **publiczne** na koncie `Laaidback`. Widoczność ma tu wymiar finansowy:

| Widoczność | Limit | Koszt crona co 5 min |
|---|---|---|
| publiczne | brak limitu minut | 0 zł |
| prywatne | 2000 min/mies | ~8640 min/mies → ok. 53 USD/mies |

GHA nalicza minimum jedną minutę na zadanie, a 8640 uruchomień miesięcznie przy prywatnym repo
przekracza darmowy limit ponad czterokrotnie. Repo publiczne ujawnia wyłącznie tytuły
obserwowanych filmów i numery kin. Token bota i identyfikator czatu trafiają do **GitHub Secrets**,
bezpiecznych również w repozytorium publicznym.

Cron GHA bywa opóźniany o kilkanaście minut przy obciążeniu platformy. Dla wykrywania nowych
seansów — dostępnych po publikacji godzinami — to akceptowalne.

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

### Etap drugi: VPS

Gdy pięć minut okaże się za rzadko: ten sam kod, timer systemd co 60 sekund,
`--state-dir /var/lib/ccdrop`. **Zero zmian w kodzie Pythona.** Dockerfile powstaje dopiero na tym
etapie — GHA go nie potrzebuje, wystarczy `setup-python`. Orientacyjny koszt: mikr.us ok. 5 zł/mies.

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
| `TELEGRAM_BOT_TOKEN` | @BotFather, komenda `/newbot` | GitHub Secrets; lokalnie `.env` |
| `TELEGRAM_CHAT_ID` | `tools/get_chat_id.py` | GitHub Secrets; lokalnie `.env` |

`.env` w `.gitignore`. Warunek działania `get_chat_id.py`: trzeba najpierw napisać cokolwiek do
swojego bota, inaczej nie ma on prawa odpisać i `getUpdates` zwróci pustkę.

## Testy

Wszystkie offline, bez sieci i bez prawdziwego Telegrama. Fixture to zapisana odpowiedź JSON
z produkcyjnego API.

`detector` — rdzeń:

- zimny start nie wysyła powiadomień,
- nowy seans dla obserwowanego filmu jest wykrywany,
- brak zmian nie generuje dropa,
- seans zniknięty i przywrócony nie wysyła się drugi raz,
- seans nieobserwowanego filmu jest ignorowany,
- dopasowanie po nazwie ignoruje wielkość liter i diakrytyki,
- dopasowanie po wyrażeniu regularnym działa na oryginalnym tytule,
- zawężenie wpisu do podzbioru kin,
- dopisanie kina do globalnej listy wywołuje zimny start tylko dla nowej pary,
- nowy wpis przy już wypełnionym `http_cache` **nie** przechodzi w `warm` z pustym baseline,
- kino bez pobranej listy dat nie ociepla żadnej ze swoich par,
- para z jedną trwale błędną datą **ociepla się mimo to** i nie zostaje zimna w nieskończoność,
- brak klucza w `watch_state` jest traktowany jak para zimna.

`main` — reguły utrwalania, najbardziej podatne na błąd:

- nieudana wysyłka nie dopisuje `seen_events`,
- nieudana wysyłka blokuje aktualizację `http_cache` w całym cyklu,
- błąd pobrania nie aktualizuje `http_cache` tej pary,
- powtórzony cykl po nieudanej wysyłce dostarcza tego samego dropa,
- nieudane pobranie **usuwa** wpis `http_cache`, więc kolejny cykl pyta bezwarunkowo,
- awaria listy dat kina zostawia wszystkie jego pary zimne,
- obecność zimnej pary wymusza pobranie bezwarunkowe, bez `If-Modified-Since`,
- `--dry-run` nie modyfikuje pliku stanu w żadnej sekcji.

`api` — parsowanie fixture'a, obsługa `304`, backoff po `429`.

`notifier` — grupowanie po (film × kino), przycięcie listy do 15 pozycji i wiersz `…i N więcej`,
mapa slug → etykieta, odmiana liczebnika, formatowanie daty w Europe/Warsaw.

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
5. Symulacja awarii: podmieniony adres Telegrama, cykl kończy się błędem wysyłki. Weryfikacja, że
   `http_cache` nie drgnął i że kolejny poprawny cykl dostarcza dropa.
6. `workflow_dispatch` w GitHub Actions — ręczne uruchomienie kończy się sukcesem i commituje stan
   na gałąź `state`. Drugie uruchomienie bez zmian repertuaru **nie** tworzy commita.
7. Obserwacja przez dobę: brak fałszywych powiadomień przy niezmienionym repertuarze.
8. **Po dobie działania dopisanie drugiego wpisu `watch`** dla filmu już granego w tym samym kinie.
   To jedyna ścieżka, o której spec sam mówi, że pierwsze uruchomienie jej nie ujawni: `http_cache`
   jest już pełny, więc bez wymuszonego pobrania bezwarunkowego nowa para ociepliłaby się z pustym
   baseline. Oczekiwane: cykl milczy, a kolejna zmiana repertuaru nie wywołuje lawiny starych
   seansów.
9. **Data, która zawiodła podczas zimnego startu.** Lokalnie, z podmienionym adresem jednej daty
   tak, by zwracała błąd. Oczekiwane: para i tak się ociepla, wpis tej daty znika z `http_cache`,
   a po przywróceniu poprawnego adresu jej seanse zostają zgłoszone **dokładnie raz**. To jedyna
   ścieżka, w której narzędzie świadomie wysyła zawyżone powiadomienie.

## Otwarte kwestie

- Token bota Telegram — do wygenerowania przez użytkownika w @BotFather. Wprowadzany bezpośrednio
  do GitHub Secrets oraz lokalnego `.env`, nigdy nie przechodzi przez historię rozmowy.
- Zawartość `config.yaml` — lista filmów i numery kin, uzupełniana przy pierwszym uruchomieniu
  z pomocą `tools/list_cinemas.py`.
