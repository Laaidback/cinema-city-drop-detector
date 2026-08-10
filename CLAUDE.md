# ccdrop — kontekst dla agenta

Detektor nowych seansów w kinach. Pilnuje repertuaru **Cinema City** i **Heliosa**, wysyła
wiadomość na Telegram, gdy dla obserwowanego filmu pojawią się nowe seanse.

Ten plik jest punktem wejścia. Uzasadnienia decyzji projektowych są w
[`docs/superpowers/specs/`](docs/superpowers/specs/) — **przeczytaj je przed zmianą czegokolwiek
w regułach utrwalania stanu.** Niemal każda z nich powstała z konkretnego scenariusza, w którym
narzędzie po cichu gubi powiadomienie na zawsze.

## Do czego to służy

Bilety na wyczekiwaną premierę w dobrej sali schodzą w godzinach. Nie ma powiadomienia o tym, że
weszły do sprzedaży — trzeba odświeżać stronę. To narzędzie robi to za użytkownika.

Sens całości to **at-least-once**: duplikat wiadomości irytuje, przegapiony seans kosztuje bilet.
Wszystkie kompromisy rozstrzygaj w tę stronę.

## Architektura

```
providers ──> Event ──> detect() ──> Drop ──> notifier
   │                       │                     │
   │                    czysty                   │
   └── api.py (Cinema City)  rdzeń      main.py decyduje, co wolno utrwalić
   └── helios.py (Helios)
```

| Moduł | Odpowiedzialność |
|---|---|
| `providers.py` | protokół `Provider` + rejestr sieci; dodanie sieci to jeden wpis |
| `api.py` | Cinema City: URL-e, parsowanie, klient HTTP z backoffem i throttlingiem |
| `helios.py` | Helios: strona → blok JS → `qjs` → `Event` |
| `chains.py` | prefiksy sieci w numerach kin (`cc:1060`, `helios:<slug>`) |
| `matching.py` | dopasowanie tytułu: fraza bez diakrytyków albo `/regex/` |
| `detector.py` | **czysty rdzeń** — co jest nowe. Zero I/O, sieci, zegara |
| `notifier.py` | formatowanie wiadomości i wysyłka |
| `state.py` | odczyt, zapis atomowy, przycinanie |
| `schedule.py` | czy ta minuta jest robocza |
| `main.py` | przepływ cyklu i **reguły utrwalania** |

Granice są celowe. `detector` nie wie, że istnieje HTTP ani Telegram. `api` nie wie, jakie filmy
są obserwowane. `main` jako jedyny decyduje, co trafia na dysk.

## Reguły, których nie wolno złamać

Pełne uzasadnienia w specyfikacji, sekcje „Reguły utrwalania stanu" i „Zimny start".

1. **Grupa dostarczona zapisuje swoje seanse; niedostarczona nie zapisuje nic.** Przy wielu
   częściach wiadomości grupa liczy się jako dostarczona tylko wtedy, gdy **wszystkie** doszły.
2. **Zimny start milczy.** Nowa para (wpis × kino) w pierwszym cyklu tylko buduje bazę. Bez tego
   pierwsze uruchomienie wysyła setki wiadomości o biletach dostępnych od tygodni.
3. **Para ociepla się tylko wtedy, gdy kino dało się zeskanować.** `fetch()` zwracające `None`
   znaczy „nie udało się" i **nie** wolno tego mylić z pustą listą. Pomyłka ociepla parę z pustą
   bazą, a przy najbliższej zmianie repertuaru wysypuje lawinę starych seansów.
4. **Stan się scala, nigdy nie zastępuje.** Data, której nie udało się pobrać, nie wnosi seansów;
   przy semantyce „zastąp" jej seanse wypadłyby ze stanu i wróciły jako fałszywe dropy.
5. **`--dry-run` nie zapisuje niczego** — ani widzianych seansów, ani flagi `warm`. Podgląd, który
   po cichu ociepla pary, zjada powiadomienie bez wysłania go.
6. **Przycinanie żyje wewnątrz `save_state`.** Nie wyciągaj go z powrotem do `main`. Gdy było
   osobnym wywołaniem, jego usunięcie przechodziło przez cały zestaw testów, bo `main` nie ma
   pokrycia. Reguła, której nie da się pominąć, bije regułę, o której trzeba pamiętać.

Zmiana klucza `watch_state` (tekst `match`, numer kina, zestaw atrybutów) **celowo** wywołuje zimny
start. Nie dopisuj migracji — jeden cichy cykl to pożądane zachowanie, nie awaria.

## Testowanie

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q
```

249 testów, wszystkie offline. Jedna asercja na test, bez „and" w nazwach.

**Reguły krytyczne weryfikuj mutacyjnie, nie samym zielonym zestawem.** W tym projekcie cztery razy
trafił się test, który wyglądał na pokrycie, a nie mógł zawieść — dwa powstały przy *naprawianiu*
poprzedniego pustego testu. Zepsuj linię, uruchom testy, sprawdź czy któryś się czerwieni,
przywróć.

**Przed pętlą mutacyjną wyczyść `__pycache__`.** CPython unieważnia `.pyc` po parze (czas
modyfikacji, rozmiar), a czas ma rozdzielczość sekundy. Mutacja neutralna rozmiarowo
(`all` → `any`, `before` ↔ `after`) zapisana w tej samej sekundzie sprawia, że pytest uruchamia
**stary bajtkod** i mutacja fałszywie wygląda na przeżytą. To się tu realnie zdarzyło.

## Rzeczy zmierzone, nie założone

Nie zgaduj o tych API — poniższe wyniki pochodzą z pomiarów na produkcji.

**Cinema City ma publiczne JSON API bez autoryzacji.** Za Cloudflare z `max-age=60`, więc
**odpytywanie częściej niż raz na minutę zwraca ten sam plik.** Cztery żądania co 12 s dały
identyczny hash przy rosnącym `age`. 60 sekund to fizyczne dno, niezależnie od hostingu.

**Żądania warunkowe są bezużyteczne.** `Last-Modified` to znacznik wygenerowania odpowiedzi, nie
odcisk treści — po wygaśnięciu cache origin zwraca `200` z nowym znacznikiem przy niezmienionym
repertuarze. `ETag` nie ma. Dlatego mechanizmu cache'owania **nie ma i nie dodawaj go**: utrwalanie
`Last-Modified` zmieniałoby plik stanu w każdym cyklu i zabiło zabezpieczenie „commit tylko przy
realnej zmianie".

**Helios nie ma publicznego API.** `api.helios.pl` wymaga uwierzytelnienia — **nie używamy go, to
prywatny interfejs.** Czytamy publiczną stronę repertuaru, z której wyciągamy osadzony blok
`window.__NUXT__` i wykonujemy go przez `qjs`. Jedno żądanie daje cały ~32-dniowy horyzont.

To źródło jest **nieoficjalne i może zmienić się bez ostrzeżenia**. Przy brakującym bloku albo
nieznanej strukturze provider loguje, czego zabrakło, i zwraca `None` — pary zostają zimne, żadnej
lawiny. Jeśli Helios przestanie działać, tu szukaj przyczyny.

Pułapka w danych Heliosa: klucze grup seansów **nie** zawsze mają postać `m<id>` — około 38% to
`e<id>` (seanse specjalne, maratony, RePlay). Kod używa pola `_id`. Założenie prefiksu `m`
zgubiłoby po cichu ponad trzecią repertuaru.

## Konfiguracja

```yaml
horizon_days: 90
cinemas: ["cc:1060", "helios:warszawa/kino-helios-blue-city"]
watch:
  - match: "Odyseja"          # fraza bez diakrytyków albo /regex/
    cinemas: ["cc:1060"]      # opcjonalne zawężenie
    attributes: [imax]        # seans musi mieć WSZYSTKIE wymienione
  - match: "/.*/"
    notify: false             # śledź do rejestru, nie wysyłaj
schedule:                     # opcjonalne; bez tego każdy przebieg pracuje
  hours: [8, 22]
  before: 2
  after: 3
```

`attributes` działa identycznie w obu sieciach, choć opisują format zupełnie inaczej: Cinema City
ma `attributeIds`, Helios nazwę sali w `cinemaScreen.feature`. Provider Heliosa mapuje ją małymi
literami do tego samego pola, więc `attributes: [dream]` i `attributes: [imax]` to jedno pojęcie.

Numery kin: `tools/list_cinemas.py`, `tools/list_helios_cinemas.py`.

## Gdzie to działa

**Na VPS-ie, nie na GitHub Actions.** Szczegóły w [`deploy/README.md`](deploy/README.md).

Workflow `check` jest **wyłączony celowo** (`DISABLED_MANUALLY`). Włączenie go przy działającym
VPS-ie oznacza dwie instancje z osobnymi plikami stanu i **każde powiadomienie przyjdzie
podwójnie**. GHA odpadł, bo mierzalnie dostarczał cron `*/5` raz na dwie godziny, z ogonem do
sześciu.

Konfiguracja wdrożenia mieszka **poza klonem repozytorium**, bo `config.yaml` jest w repo i
edytowanie go w katalogu roboczym blokowało `git pull`.

## Stan bieżący: tryb pomiarowy

Uwaga, to **stan tymczasowy**. Odpytywanie chodzi **co minutę, całodobowo**, a w konfiguracji jest
wpis `/.*/` z `notify: false`, który obserwuje cały repertuar obu kin bez wysyłania czegokolwiek.

Cel: ustalić, **o których godzinach kina publikują nowe seanse**. Odczyt:

```bash
.venv/bin/python tools/drop_hours.py <katalog-stanu>
```

Gdy dane odpowiedzą na pytanie, wracamy do okna 58–03 wokół pełnej godziny w godzinach 8–22. To
różnica ~56 000 żądań dziennie wobec ~3 500. Wpis w cronie na serwerze zawiera komentarz
z instrukcją powrotu.

## Pułapki, na które ktoś już wpadł

- **Świeża instalacja może paść, choć u Ciebie działa.** Dodanie katalogu najwyższego poziomu
  rozbiło automatyczne wykrywanie pakietów setuptools; lokalne środowisko tego nie pokazało, bo
  powstało wcześniej. `pyproject.toml` ma teraz jawne `packages = ["ccdrop"]`. Po dodaniu nowego
  katalogu **sprawdź instalację w czystym venv**.
- **Telegram tnie wiadomości po 4096 znakach.** Długie dropy dzielimy na części z odstępem 1,2 s,
  bo limit to około jedna wiadomość na sekundę do czatu. Bez odstępu duży drop dostaje `429`, kod
  czyta to jako porażkę i ponawia całość — przy dostatecznie dużym dropie w nieskończoność.
- **Godzin seansów nie konwertuj między strefami.** `eventDateTime` jest już czasem lokalnym kina.
  Strefa Europe/Warsaw ma znaczenie wyłącznie przy liczeniu „dziś" i okna harmonogramu, bo serwer
  może chodzić w UTC.
- **`--force-send` dopisuje stan po udanej wysyłce.** Nie omija reguł utrwalania i nie ociepla par
  zimnych — para zimna nie wyśle nic, mimo flagi.

## Konwencje

- Bez komentarzy wyjaśniających w kodzie; kod ma być samoopisujący się.
- Wszystkie teksty widziane przez użytkownika po polsku, z odmianą liczebnika
  (`1 nowy seans`, `2–4 nowe seanse`, `5+ nowych seansów`, końcówki 12–14 dopełniaczowo).
- Skróty dni tygodnia z własnej mapy, nie z `locale` — locale bywa niedostępne w kontenerze.
- Sekrety nigdy w repozytorium ani w historii rozmowy. Na serwerze plik `600` poza klonem.
