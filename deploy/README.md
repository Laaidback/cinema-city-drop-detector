# Wdrożenie na VPS (mikr.us, Alpine Linux)

Tak wygląda **realne** wdrożenie: kontener LXC z Alpine, busybox `crond` jako harmonogram,
wszystko w katalogu domowym jednego nieuprzywilejowanego użytkownika. Bez systemd, bez roota,
bez Dockera.

Ścieżka Debian/Ubuntu z systemd jest opisana na końcu jako alternatywa na przyszłość. Pliki
`deploy/ccdrop.service` i `deploy/ccdrop.timer` zostają w repozytorium właśnie po to i **dziś
nic ich nie używa** — nie szukaj ich na maszynie, tam nie ma nawet `systemctl`.

## Maszyna

| | |
|---|---|
| Plan | mikr.us **FROG**, ok. 35 zł/rok (kolejny plan w cenniku to 1.0) |
| Zasoby | 256 MB RAM, ok. 2,9 GB dysku, 1 rdzeń, kontener LXC |
| Host | `frog01.mikr.us`, SSH na porcie **11237** |
| Użytkownik | `frog`, uid 1000, grupa `wheel` |
| System | Alpine Linux v3.23, pakiety przez `apk`, init OpenRC |
| Harmonogram | busybox `crond` — **systemd tu nie istnieje** |
| Python | 3.12.12 z obrazu; projekt wymaga ≥ 3.10 |

```sh
ssh -p 11237 frog@frog01.mikr.us
```

Te liczby wyznaczają wszystkie dalsze decyzje. 256 MB RAM i 2,9 GB dysku nie mieszczą Dockera ani
Node'a, a jeden rdzeń nie lubi procesu chodzącego dłużej niż odstęp między uruchomieniami.

## Dlaczego wszystko bez roota

`sudo` jest zainstalowane, ale **pyta o hasło**, więc nie da się go użyć z crona ani z żadnego
skryptu bez interakcji. Zamiast obchodzić to wpisem w `/etc/sudoers.d`, całe wdrożenie jest
bezrootowe: kod, virtualenv, konfiguracja, sekrety, stan, log i wpis crontaba należą do
użytkownika `frog` i leżą w `$HOME`.

Jedyny wyjątek to instalacja jednego pakietu, wykonywana raz i ręcznie:

```sh
sudo apk add quickjs
```

Poza tym poleceniem żaden krok z tej instrukcji nie wymaga hasła (wariant systemd na końcu jest
osobną historią i wymaga roota od początku do końca). Jeśli któryś krok nagle poprosi o hasło —
to znak, że coś jest robione nie tam, gdzie powinno.

## quickjs jest wymagany, nie opcjonalny

Strona repertuaru Heliosa nie zwraca JSON-a. Osadza stan w zminifikowanym IIFE
`window.__NUXT__`, więc odczytanie go wymaga **wykonania** tego kodu — `ccdrop/helios.py`
uruchamia do tego `qjs` (ok. 1 MB).

Bez binarki `qjs` provider Heliosa loguje ostrzeżenie i zwraca `None`. Kino jest wtedy pomijane
w cyklu, jego pary zostają zimne i **żadne powiadomienie o Heliosie nie przyjdzie**, choć Cinema
City działa dalej i nic w logu nie krzyczy błędem. Z punktu widzenia użytkownika awaria jest
cicha, dlatego to pierwsza rzecz do sprawdzenia po instalacji:

```sh
command -v qjs
```

Node.js odrzucony świadomie: ok. 60 MB na dysku wobec ok. 1 MB `qjs`, za dokładnie to samo zadanie.
Przy 2,9 GB dysku to nie jest szczegół.

## Rozkład katalogów

Wszystko pod `$HOME`, bo nic nie działa z rootem:

| Co | Gdzie |
|---|---|
| kod | `~/ccdrop` (klon publicznego repozytorium) |
| virtualenv | `~/ccdrop/.venv` |
| konfiguracja | `~/.config/ccdrop/config.yaml`, `chmod 600` |
| sekrety | `~/.config/ccdrop/env`, `chmod 600` |
| stan | `~/.local/state/ccdrop/seen.json` |
| log | `~/.local/state/ccdrop/ccdrop.log` |

### Konfiguracja musi leżeć poza checkoutem

`config.yaml` jest **plikiem śledzonym w repozytorium**. Pierwsza wersja wdrożenia edytowała go
w miejscu, w klonie — i pierwszy `git pull` przerwał się konfliktem scalania na tym pliku, bo
lokalna zmiana zderzyła się ze zmianą z `main`. Aktualizacja kodu wymagałaby wtedy ręcznego
rozwiązywania konfliktu przy każdym wydaniu, a przy nieuważnym `checkout --ours` można zgubić
całą konfigurację wdrożeniową.

Dlatego konfiguracja produkcyjna leży w `~/.config/ccdrop/config.yaml` i jest podawana jawnie
przez `--config`. `config.yaml` w klonie pozostaje wersją przykładową, nikt go nie rusza,
`git pull` zawsze przechodzi bez konfliktu.

Ta sama reguła dotyczy stanu i logu: `--state-dir` wskazuje `~/.local/state/ccdrop`, nigdy
katalog `state/` w klonie.

## Instalacja

```sh
sudo apk add quickjs
git clone https://github.com/Laaidback/cinema-city-drop-detector.git ~/ccdrop
python3 -m venv ~/ccdrop/.venv
~/ccdrop/.venv/bin/pip install --upgrade pip
~/ccdrop/.venv/bin/pip install -e ~/ccdrop
mkdir -p ~/.config/ccdrop ~/.local/state/ccdrop
```

`git` i `python3` są już w obrazie — `quickjs` to jedyny brakujący pakiet.

Klon po **HTTPS**, nie po SSH: repozytorium jest publiczne, więc odczyt nie potrzebuje klucza,
a VPS nigdy nic nie pushuje. Na maszynie nie ma i nie powinno być klucza SSH do GitHuba ani
tożsamości gita.

## Sekrety

```sh
install -m 600 /dev/null ~/.config/ccdrop/env
cat > ~/.config/ccdrop/env <<'EOF'
TELEGRAM_BOT_TOKEN=<token-od-BotFathera>
TELEGRAM_CHAT_ID=<id-czatu-z-tools/get_chat_id.py>
EOF
```

`install -m 600` **przed** zapisem, nie `chmod` po — inaczej sekret przez chwilę leży z prawami
domyślnymi. Format to zwykłe `KLUCZ=wartość`, bez `export` i bez cudzysłowów, żeby ten sam plik
nadawał się także jako `EnvironmentFile` w wariancie systemd.

Detektor czyta `TELEGRAM_BOT_TOKEN` i `TELEGRAM_CHAT_ID` ze środowiska. Gdy któregoś brakuje,
kończy się natychmiast komunikatem `Brak zmiennej środowiskowej` — z wyjątkiem `--dry-run`,
który notyfikatora wcale nie buduje.

## Konfiguracja

```sh
cp ~/ccdrop/config.yaml ~/.config/ccdrop/config.yaml
chmod 600 ~/.config/ccdrop/config.yaml
```

Dalej edytuj już tylko kopię w `~/.config/ccdrop/`. Numery kin wypisują
`tools/list_cinemas.py` (Cinema City) i `tools/list_helios_cinemas.py` (Helios); identyfikatory
w konfiguracji noszą prefiks sieci (`cc:1060`, `helios:warszawa/kino-helios-blue-city`), a wartość
bez prefiksu normalizuje się do `cc`.

Sekcja `schedule` jest opcjonalna i decyduje, czy dana minuta jest „robocza". Poza oknem proces
kończy się kodem 0 po jednej linii w logu, bez ani jednego żądania HTTP i bez dotknięcia pliku
stanu:

```yaml
schedule:
  hours: [8, 22]
  before: 2
  after: 3
```

Powyższe daje okna 07:58–08:03, 08:58–09:03, …, 21:58–22:03. Godziny liczone są zawsze w strefie
`Europe/Warsaw`, niezależnie od strefy kontenera, więc zmiana czasu letni/zimowy nie przesuwa
okien — sam crontab tego nie umie i to jest główny powód, żeby okno opisywać w konfiguracji,
a nie tylko w cronie.

Ograniczenia: `hours` to dwie liczby 0–23, początek nie może być późniejszy niż koniec, `before`
i `after` nie mogą być ujemne, a ich suma musi być mniejsza niż 59 (inaczej okna nachodziłyby
na siebie).

## Crontab

Harmonogramem jest busybox `crond` z obrazu — działa bez naszego udziału:

```sh
pgrep crond
```

Crontab użytkownika `frog` instaluj w całości, z pliku, a nie przez `crontab -e` (w Alpine
`$EDITOR` to `vi`):

```sh
crontab - <<'EOF'
# pomiar: co minutę, całą dobę
* * * * * cd /home/frog/ccdrop && set -a && . /home/frog/.config/ccdrop/env && set +a && /home/frog/ccdrop/.venv/bin/python -m ccdrop.main --config /home/frog/.config/ccdrop/config.yaml --state-dir /home/frog/.local/state/ccdrop >> /home/frog/.local/state/ccdrop/ccdrop.log 2>&1
# przycięcie logu: zostaw 5000 ostatnich wierszy
0 4 * * * tail -n 5000 /home/frog/.local/state/ccdrop/ccdrop.log > /home/frog/.local/state/ccdrop/ccdrop.log.tmp && mv /home/frog/.local/state/ccdrop/ccdrop.log.tmp /home/frog/.local/state/ccdrop/ccdrop.log
EOF
```

Cztery rzeczy w tych dwóch wierszach nie są kosmetyczne:

- **Ścieżki bezwzględne, wszędzie.** Busybox w cronie nie rozwija `$HOME` w sposób, na którym
  można polegać, a `~` nie jest rozwijane w ogóle. Wiersze są od tego długie i **nie wolno ich
  zawijać** — `crond` czyta jeden wiersz na wpis.
- **`set -a` wokół wczytania sekretów.** Samo `. plik` ustawiłoby zmienne powłoki, ale ich nie
  wyeksportowało, więc proces Pythona i tak zakończyłby się na brakującej zmiennej.
- **Przekierowanie do pliku.** Busybox `crond` nie wysyła maila z wyjściem zadania; bez `>>`
  wszystko, co detektor wypisze, przepada.
- **Przycinanie logu przez plik tymczasowy i `mv`.** `tail` piszący wprost do własnego wejścia
  najpierw obciąłby je do zera. Ograniczenie do 5000 wierszy jest konieczne, bo przy odpytywaniu
  co minutę log rośnie bez końca, a dysku jest 2,9 GB.

Cron ustala tylko, **kiedy proces wstaje**. O tym, czy minuta jest robocza, decyduje sekcja
`schedule` w konfiguracji — te dwa mechanizmy są komplementarne, patrz „Tryby pracy".

## Weryfikacja

```sh
crontab -l                                    # czy wpisy w ogóle są
command -v qjs                                # bez tego Helios milczy
tail -n 50 ~/.local/state/ccdrop/ccdrop.log   # ostatnie przebiegi
tail -f ~/.local/state/ccdrop/ccdrop.log      # podgląd na żywo
```

W logu udanego cyklu jest linia `Pobrano N seansów, wykryto M grup`. Poza oknem harmonogramu —
jedna linia `poza oknem harmonogramu, cykl pominięty`.

Przebieg na żądanie, bez wysyłki i **bez zapisu stanu** (respektuje okno, więc poza nim tylko
się przywita):

```sh
~/ccdrop/.venv/bin/ccdrop --config ~/.config/ccdrop/config.yaml \
  --state-dir ~/.local/state/ccdrop --dry-run --verbose
```

Sprawdź jeszcze, że obie sieci faktycznie odpowiadają:

```sh
grep -c 'Helios:' ~/.local/state/ccdrop/ccdrop.log   # oczekiwane 0
ls -l ~/.local/state/ccdrop/seen.json                # stan istnieje i rośnie
```

Każde ostrzeżenie z prefiksem `Helios:` znaczy, że kino tej sieci zostało pominięte w cyklu.
Jednorazowe jest normalne (strona bywa niedostępna), powtarzalne oznacza brak `qjs` albo zmianę
kształtu strony.

Rozkład godzin, o których kina publikują repertuar:

```sh
~/ccdrop/.venv/bin/python ~/ccdrop/tools/drop_hours.py ~/.local/state/ccdrop
```

## Aktualizacja

```sh
git -C ~/ccdrop pull
~/ccdrop/.venv/bin/pip install -e ~/ccdrop
```

Nic nie trzeba restartować: nie ma demona trzymającego kod w pamięci, następne uruchomienie
z crona bierze nową wersję. `pip install -e` jest potrzebny tylko wtedy, gdy zmieniły się
zależności albo metadane pakietu — instalacja edytowalna wskazuje na katalog klonu, więc sam
kod Pythona jest aktualny od razu po `pull`.

Konfiguracja i sekrety są poza klonem, więc `pull` ich nie dotyczy. Gdy wydanie dodaje nowe
pole konfiguracji, trzeba je dopisać do `~/.config/ccdrop/config.yaml` ręcznie.

## Tryby pracy

Dwa poziomy działają razem: **cron** ogranicza liczbę wybudzeń (a więc zużycie CPU i pamięci),
**`schedule`** jest ostateczną instancją decydującą o tym, czy cykl się wykona.

### Pomiar — tryb obecny

```crontab
* * * * *
```

W konfiguracji **nie ma** sekcji `schedule`, a lista `watch` zawiera wpis łapiący wszystko
(`match: "/.*/"`, `notify: false`) obok wpisów, o których naprawdę chcemy dostawać wiadomości.
Cel jest jeden: zmierzyć, o których godzinach kina publikują repertuar, zamiast zgadywać.
To stan **tymczasowy** — ok. 56 000 żądań HTTP na dobę.

### Okno wokół pełnej godziny — tryb docelowy

```crontab
58,59,0,1,2,3 * * * *
```

plus sekcja `schedule` z przykładu wyżej. Cron budzi proces 144 razy na dobę, a `schedule`
przepuszcza tylko okna między 08:00 a 22:00 — ok. 90 pełnych cykli i ok. 3 500 żądań na dobę,
czyli szesnaście razy mniej niż w trybie pomiarowym.

### Przełączenie

1. Dopisz sekcję `schedule` do `~/.config/ccdrop/config.yaml`.
2. Podmień minuty w pierwszym wierszu crontaba na `58,59,0,1,2,3`.
3. Usuń wpis `notify: false` z listy `watch`, jeśli pomiar jest już niepotrzebny — inaczej
   `drop_log` dalej rośnie o obserwacje całego repertuaru.

Kolejność ma znaczenie tylko w jednym miejscu: zawężenie crona **przed** dopisaniem `schedule`
jest bezpieczne, odwrotnie też — najgorsze, co się stanie, to kilka cykli więcej lub mniej.
Żadna zmiana nie ociepla ani nie wyzimnia par, bo klucze `watch_state` zależą od wpisów `watch`,
nie od harmonogramu.

## Zmierzony ślad

| Metryka | Wartość |
|---|---|
| szczytowy RSS jednego cyklu | ok. 49 MB (z 256 MB) |
| instalacja (kod + venv) | 19,7 MB |
| plik stanu | 34 KB |
| pełny cykl, obie sieci | ok. 10 s, ok. 39 żądań HTTP |

Cykl trwa ok. 10 s, więc przy odpytywaniu co minutę uruchomienia nigdy się nie nakładają —
dlatego nie ma tu żadnej blokady ani `flock`. Gdyby częstotliwość kiedyś zeszła poniżej czasu
cyklu, blokada stałaby się konieczna: dwa procesy pisałyby ten sam plik stanu.

Podział 39 żądań: Cinema City to jedno o listę kin, jedno o listę dat i po jednym na każdy
grany dzień (przy jednym kinie i ok. 35 dniach repertuaru — 37). Helios to dwa żądania łącznie,
bo jedna strona repertuaru niesie cały horyzont.

## GitHub Actions musi zostać wyłączony

Workflow `check` jest w stanie **`DISABLED_MANUALLY`** i to jest stan docelowy, nie zaniedbanie.

Ponowne włączenie go przy działającym VPS-ie daje **dwie instancje z osobnymi plikami stanu**.
Żadna nie wie o drugiej, każda wykryje ten sam drop niezależnie i **każda wyśle powiadomienie** —
wszystko przyjdzie podwójnie. Runner dodatkowo commitowałby stan na gałąź `state`, która przy
wdrożeniu na VPS nie odzwierciedla już niczego rzeczywistego.

Sekcja `schedule` w konfiguracji **nie jest** zabezpieczeniem: repozytorium ma własny
`config.yaml` bez tej sekcji, a nawet gdyby ją miało, nieregularnie dostarczany cron GHA czasem
trafiłby w okno i wysłał duplikat.

Gdzie to sprawdzić: `Actions` → `check` → menu `···`. Jeśli widnieje **Enable workflow**,
workflow jest wyłączony i tak ma zostać.

## Zatrzymanie

Zakomentuj wiersz detektora w crontabie:

```sh
crontab -l > /tmp/cron && sed -i 's|^\* \* \* \* \*|#&|' /tmp/cron && crontab /tmp/cron
```

Nie `crontab -r` — to usuwa **cały** crontab razem z przycinaniem logu i nie zostawia śladu,
z czego trzeba go potem odtworzyć.

Stan zostaje na dysku, więc po ponownym włączeniu pary są dalej ciepłe i nie ma lawiny
„nowych" seansów sprzed przerwy. Usunięcie `~/.local/state/ccdrop/seen.json` to świadomy zimny
start: pierwszy cykl po nim zapisuje baseline i milczy.

---

## Alternatywa: Debian/Ubuntu + systemd (dziś nieużywana)

`deploy/ccdrop.service` i `deploy/ccdrop.timer` opisują wariant z systemd. **Nie są używane na
obecnej maszynie** i nie da się ich tam użyć — Alpine startuje OpenRC. Zostają w repozytorium
na wypadek przeniesienia projektu na obraz z systemd; wtedy dają dwie rzeczy, których busybox
cron nie ma: hartowanie procesu (`ProtectSystem=strict`, `SystemCallFilter`, osobny użytkownik
systemowy) i log w journalu zamiast pliku przycinanego `tail`em.

Wariant ten zakłada roota i ścieżki systemowe, więc rozkład katalogów jest inny niż powyżej:
kod w `/opt/ccdrop`, stan w `/var/lib/ccdrop`, sekrety w `/etc/ccdrop/ccdrop.env`, konto
systemowe `ccdrop`.

```bash
apt update && apt install -y git python3 python3-venv quickjs
useradd --system --home-dir /opt/ccdrop --shell /usr/sbin/nologin ccdrop
git clone https://github.com/Laaidback/cinema-city-drop-detector.git /opt/ccdrop
python3 -m venv /opt/ccdrop/.venv
/opt/ccdrop/.venv/bin/pip install -e /opt/ccdrop
chown -R ccdrop:ccdrop /opt/ccdrop
install -d -o ccdrop -g ccdrop -m 750 /var/lib/ccdrop

install -d -o root -g root -m 755 /etc/ccdrop
install -m 600 /dev/null /etc/ccdrop/ccdrop.env   # TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

cp /opt/ccdrop/deploy/ccdrop.service /etc/systemd/system/
cp /opt/ccdrop/deploy/ccdrop.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now ccdrop.timer
```

Trzy uwagi do tego wariantu:

- `EnvironmentFile` czyta systemd jako root, przed zrzuceniem uprawnień do użytkownika `ccdrop`,
  więc plik sekretów nie musi być czytelny dla nikogo poza rootem. To jedyna przewaga nad
  wariantem bezrootowym, gdzie sekrety musi czytać sam `frog`.
- Timer włącza usługę sam (`Type=oneshot`), `ccdrop.service` nie wymaga `enable`.
- `ExecStart` w unicie **nie podaje** `--config`, więc konfiguracja czytana jest z
  `WorkingDirectory`, czyli z klonu — czyli dokładnie z tego pliku, który konfliktuje przy
  `git pull`. Przenosząc projekt na systemd, dopisz `--config /etc/ccdrop/config.yaml`.

Weryfikacja i aktualizacja jak zwykle w systemd: `systemctl start ccdrop.service`,
`systemctl list-timers ccdrop.timer`, `journalctl -u ccdrop -f`, a po `git pull` dodatkowo
`chown -R ccdrop:ccdrop /opt/ccdrop`.
