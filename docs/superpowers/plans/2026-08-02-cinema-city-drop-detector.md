# Cinema City drop detector — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Narzędzie, które cyklicznie sprawdza repertuar Cinema City i wysyła na Telegram
powiadomienie, gdy dla obserwowanego filmu pojawią się nowe seanse.

**Architecture:** Czysty rdzeń (`detector`) liczy, co jest nowe, na podstawie stanu i świeżo
pobranych danych — bez I/O. Cienkie adaptery obsługują HTTP, plik stanu i Telegram. `main` jako
jedyny decyduje, co wolno utrwalić, według tabeli reguł ze specyfikacji.

**Tech Stack:** Python 3.12, `requests`, `PyYAML`, `pytest`. Uruchamianie: GitHub Actions cron,
stan na gałęzi `state`.

**Spec:** `docs/superpowers/specs/2026-08-02-cinema-city-drop-detector-design.md` — przeczytaj przed
startem. Reguły utrwalania stanu są tam wyprowadzone z konkretnych scenariuszy awarii; ten plan je
wykonuje, ale nie powtarza uzasadnień.

**Uwaga o commitach:** każde zadanie kończy się commitem. Zatwierdzenie tego planu jest zgodą na te
commity. Push na GitHub następuje dopiero w zadaniu 17.

---

## Struktura plików

| Plik | Odpowiedzialność |
|---|---|
| `ccdrop/models.py` | niemutowalne dataclassy: `Event`, `WatchEntry`, `Config`, `Drop`, `WatchState`, `State` |
| `ccdrop/config.py` | wczytanie i walidacja `config.yaml` |
| `ccdrop/matching.py` | normalizacja tytułów i dopasowanie `match` → nazwa filmu |
| `ccdrop/state.py` | odczyt, zapis atomowy, deterministyczna serializacja, przycinanie |
| `ccdrop/detector.py` | czysty rdzeń: `cold_cinemas()` i `detect()` |
| `ccdrop/api.py` | klient HTTP: budowa URL-i, warunkowe GET-y, throttle, backoff, parsowanie |
| `ccdrop/notifier.py` | formatowanie wiadomości i wysyłka na Telegram |
| `ccdrop/main.py` | argumenty CLI, przepływ cyklu, reguły utrwalania |
| `tools/list_cinemas.py` | wypisuje numery i nazwy kin |
| `tools/get_chat_id.py` | wypisuje `TELEGRAM_CHAT_ID` |
| `.github/workflows/check.yml` | cron, sekrety, commit stanu na gałąź `state` |

`matching.py` jest wydzielony z `detector.py`, bo normalizacja diakrytyków i dwa tryby dopasowania
to samodzielna odpowiedzialność z własnym zestawem przypadków brzegowych.

---

## Task 1: Repozytorium i izolacja od konta firmowego

**Files:**
- Create: `.gitignore`, `README.md`
- Modify: `~/.ssh/config`

- [ ] **Step 1: Wygeneruj osobny klucz SSH**

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_personal -C "Laaidback" -N ""
```

Klucz firmowy `~/.ssh/id_ed25519` zostaje nietknięty. Osobny jest konieczny, bo GitHub nie pozwala
wpiąć tego samego klucza do dwóch kont.

- [ ] **Step 2: Dodaj alias hosta**

Dopisz do `~/.ssh/config`:

```
Host github-personal
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_personal
  IdentitiesOnly yes
```

`IdentitiesOnly yes` jest istotne — bez tego SSH zaproponuje najpierw klucz firmowy i GitHub
zaloguje na złe konto.

- [ ] **Step 3: Wypisz klucz publiczny do wklejenia**

```bash
cat ~/.ssh/id_ed25519_personal.pub
```

Użytkownik wkleja go na `https://github.com/settings/keys`. **To krok ręczny — zatrzymaj się i
poproś o potwierdzenie.**

- [ ] **Step 4: Zweryfikuj, że alias trafia na właściwe konto**

```bash
ssh -T git@github-personal
```

Oczekiwane: `Hi Laaidback! You've successfully authenticated...`
Jeśli w odpowiedzi jest inny login — konfiguracja wskazuje konto firmowe, nie idź dalej.

- [ ] **Step 5: Zainicjuj repozytorium z lokalną tożsamością**

```bash
cd ~/projects/cinema-city-drop-detector
git init -b main
git config --local user.name "Krystian"
git config --local user.email "24231775+Laaidback@users.noreply.github.com"
git config --local commit.gpgsign false
```

`commit.gpgsign false` jest konieczne — globalnie włączone podpisywanie użyłoby klucza firmowego.

- [ ] **Step 6: Zweryfikuj, że ustawienia lokalne wygrywają**

```bash
git config user.email && git config commit.gpgsign
```

Oczekiwane: adres noreply oraz `false`.

- [ ] **Step 7: Utwórz `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.env
state/
.pytest_cache/
```

`state/` jest ignorowany lokalnie — na GHA stan żyje na osobnej gałęzi, a lokalne przebiegi nie mają
zaśmiecać repo.

- [ ] **Step 8: Utwórz `README.md`**

```markdown
# Cinema City drop detector

Pilnuje repertuaru Cinema City i wysyła powiadomienie na Telegram, gdy dla obserwowanego filmu
pojawią się nowe seanse.

- Co śledzić: `config.yaml`
- Projekt i uzasadnienia decyzji: `docs/superpowers/specs/`
- Uruchamianie: GitHub Actions co 5 minut, stan na gałęzi `state`
```

- [ ] **Step 9: Commit**

```bash
git add .gitignore README.md
git commit -m "chore: init repository"
```

---

## Task 2: Szkielet projektu i pytest

**Files:**
- Create: `pyproject.toml`, `ccdrop/__init__.py`, `tests/__init__.py`, `tests/test_smoke.py`

- [ ] **Step 1: Utwórz `pyproject.toml`**

```toml
[project]
name = "ccdrop"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["requests>=2.32", "PyYAML>=6.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Utwórz katalogi pakietów**

```bash
mkdir -p ccdrop tests
touch ccdrop/__init__.py tests/__init__.py
```

Musi się to zdarzyć **przed** instalacją. Editable install przy nieistniejącym `ccdrop/` kończy się
sukcesem, ale nie mapuje pakietu — `import ccdrop` nadal zawodzi i trzeba instalować ponownie.

- [ ] **Step 3: Utwórz środowisko i zainstaluj**

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

- [ ] **Step 4: Napisz test dymny**

`tests/test_smoke.py`:

```python
def test_package_imports():
    import ccdrop

    assert ccdrop is not None
```

- [ ] **Step 5: Uruchom testy**

Run: `.venv/bin/pytest -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml ccdrop tests
git commit -m "chore: add project skeleton and pytest"
```

---

## Task 3: Modele domenowe

**Files:**
- Create: `ccdrop/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Napisz failujący test**

```python
from ccdrop.models import Event


def test_event_is_immutable():
    event = Event(
        id="1600867",
        film_id="8099d2r",
        film_name="Backrooms",
        cinema_id="1090",
        business_day="2026-08-15",
        date_time="2026-08-15T18:30:00",
        auditorium="Sala 4",
        booking_link="https://tickets.cinema-city.pl/api/order/1600867",
        attribute_ids=("imax",),
    )

    with pytest.raises(FrozenInstanceError):
        event.id = "inny"
```

Dopisz importy `pytest` oraz `from dataclasses import FrozenInstanceError`.

- [ ] **Step 2: Uruchom test**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ccdrop.models'`

- [ ] **Step 3: Zaimplementuj modele**

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Event:
    id: str
    film_id: str
    film_name: str
    cinema_id: str
    business_day: str
    date_time: str
    auditorium: str
    booking_link: str
    attribute_ids: tuple[str, ...]


@dataclass(frozen=True)
class WatchEntry:
    match: str
    cinemas: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Config:
    horizon_days: int
    cinemas: tuple[str, ...]
    watch: tuple[WatchEntry, ...]


@dataclass(frozen=True)
class Drop:
    watch_key: str
    film_name: str
    cinema_id: str
    events: tuple[Event, ...]


@dataclass
class WatchState:
    warm: bool = False
    seen_events: dict[str, str] = field(default_factory=dict)


@dataclass
class State:
    watch_state: dict[str, WatchState] = field(default_factory=dict)
    http_cache: dict[str, str] = field(default_factory=dict)
    cinema_names: dict[str, str] = field(default_factory=dict)
```

`Drop` niesie `watch_key`, bo po udanej wysyłce `main` musi wiedzieć, do którego wpisu dopisać
widziane seanse.

- [ ] **Step 4: Uruchom test**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ccdrop/models.py tests/test_models.py
git commit -m "feat: add domain models"
```

---

## Task 4: Dopasowywanie tytułów

**Files:**
- Create: `ccdrop/matching.py`
- Test: `tests/test_matching.py`

Zgodnie ze specyfikacją: tryb frazy ignoruje wielkość liter i diakrytyki, tryb regex działa na
oryginalnym tytule przez `re.search`.

- [ ] **Step 1: Napisz failujące testy**

Jeden assert na test, nazwy bez „i".

```python
from ccdrop.matching import matches


def test_phrase_matches_substring():
    assert matches("Backrooms", "Backrooms. Bez wyjścia")


def test_phrase_ignores_case():
    assert matches("backrooms", "Backrooms. Bez wyjścia")


def test_phrase_ignores_diacritics():
    assert matches("Zolw", "Żółw w wielkim mieście")


def test_phrase_rejects_unrelated_title():
    assert not matches("Backrooms", "Diuna 3")


def test_regex_mode_anchors():
    assert matches("/^Diuna.*3$/", "Diuna część 3")


def test_regex_mode_respects_anchors():
    assert not matches("/^Diuna.*3$/", "Nowa Diuna 3 IMAX")


def test_regex_mode_keeps_diacritics():
    assert matches("/Żółw/", "Żółw w wielkim mieście")
```

- [ ] **Step 2: Uruchom testy**

Run: `.venv/bin/pytest tests/test_matching.py -v`
Expected: FAIL — brak modułu

- [ ] **Step 3: Zaimplementuj**

```python
import re
import unicodedata


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return without_marks.casefold().replace("ł", "l")


def matches(pattern: str, film_name: str) -> bool:
    if len(pattern) >= 2 and pattern.startswith("/") and pattern.endswith("/"):
        return re.search(pattern[1:-1], film_name) is not None
    return normalize(pattern) in normalize(film_name)
```

`ł` wymaga osobnej obsługi — nie jest literą z dołączonym znakiem diakrytycznym, więc `NFKD` go nie
rozkłada i sam `unicodedata` by go nie usunął.

- [ ] **Step 4: Uruchom testy**

Run: `.venv/bin/pytest tests/test_matching.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add ccdrop/matching.py tests/test_matching.py
git commit -m "feat: add title matching with diacritics folding"
```

---

## Task 5: Wczytywanie konfiguracji

**Files:**
- Create: `ccdrop/config.py`, `config.yaml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Napisz failujące testy**

```python
import pytest

from ccdrop.config import load_config


def test_loads_horizon(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n")

    assert load_config(path).horizon_days == 90


def test_cinema_ids_are_strings(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n")

    assert load_config(path).cinemas == ("1090",)


def test_entry_cinemas_default_to_none(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: Backrooms\n")

    assert load_config(path).watch[0].cinemas is None


def test_rejects_empty_watch(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("horizon_days: 90\ncinemas: [1090]\nwatch: []\n")

    with pytest.raises(ValueError, match="watch"):
        load_config(path)


def test_rejects_entry_cinema_outside_global_list(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(
        "horizon_days: 90\ncinemas: [1090]\nwatch:\n  - match: X\n    cinemas: [9999]\n"
    )

    with pytest.raises(ValueError, match="9999"):
        load_config(path)
```

Numery kin trzymamy jako łańcuchy, bo API zwraca je jako łańcuchy i klucze stanu muszą się zgadzać.
YAML wczytałby `1090` jako liczbę, co dałoby klucze `Backrooms|1090` i `Backrooms|'1090'` w zależności
od źródła.

- [ ] **Step 2: Uruchom testy**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL

- [ ] **Step 3: Zaimplementuj**

```python
from pathlib import Path

import yaml

from ccdrop.models import Config, WatchEntry


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}

    cinemas = tuple(str(c) for c in raw.get("cinemas", []))
    if not cinemas:
        raise ValueError("cinemas: lista nie może być pusta")

    entries_raw = raw.get("watch") or []
    if not entries_raw:
        raise ValueError("watch: lista nie może być pusta")

    entries = []
    for item in entries_raw:
        match = item.get("match")
        if not match:
            raise ValueError("watch: każdy wpis wymaga pola match")
        own = item.get("cinemas")
        own_ids = tuple(str(c) for c in own) if own else None
        for cinema in own_ids or ():
            if cinema not in cinemas:
                raise ValueError(f"watch/{match}: kino {cinema} spoza globalnej listy cinemas")
        entries.append(WatchEntry(match=match, cinemas=own_ids))

    return Config(
        horizon_days=int(raw.get("horizon_days", 90)),
        cinemas=cinemas,
        watch=tuple(entries),
    )
```

- [ ] **Step 4: Uruchom testy**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: 5 passed

- [ ] **Step 5: Utwórz przykładowy `config.yaml`**

```yaml
horizon_days: 90
cinemas: [1090]
watch:
  - match: "Backrooms"
```

- [ ] **Step 6: Commit**

```bash
git add ccdrop/config.py tests/test_config.py config.yaml
git commit -m "feat: add config loading and validation"
```

---

## Task 6: Stan — odczyt, zapis, przycinanie

**Files:**
- Create: `ccdrop/state.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Napisz failujące testy**

```python
from ccdrop.models import State, WatchState
from ccdrop.state import load_state, prune, save_state


def test_roundtrip_preserves_seen_events(tmp_path):
    state = State(watch_state={"A|1": WatchState(warm=True, seen_events={"1": "2026-08-15"})})
    save_state(tmp_path, state)

    assert load_state(tmp_path).watch_state["A|1"].seen_events == {"1": "2026-08-15"}


def test_missing_file_gives_empty_state(tmp_path):
    assert load_state(tmp_path).watch_state == {}


def test_corrupted_file_gives_empty_state(tmp_path):
    (tmp_path / "seen.json").write_text("{ to nie jest json")

    assert load_state(tmp_path).watch_state == {}


def test_serialization_is_deterministic(tmp_path):
    first = State(http_cache={"b|2": "x", "a|1": "y"})
    second = State(http_cache={"a|1": "y", "b|2": "x"})
    save_state(tmp_path, first)
    first_bytes = (tmp_path / "seen.json").read_bytes()
    save_state(tmp_path, second)

    assert (tmp_path / "seen.json").read_bytes() == first_bytes


def test_prune_drops_past_events():
    state = State(
        watch_state={"A|1": WatchState(warm=True, seen_events={"old": "2026-07-01", "new": "2026-09-01"})}
    )

    assert prune(state, today="2026-08-02").watch_state["A|1"].seen_events == {"new": "2026-09-01"}


def test_prune_drops_past_http_cache():
    state = State(http_cache={"1090|2026-07-01": "x", "1090|2026-09-01": "y"})

    assert prune(state, today="2026-08-02").http_cache == {"1090|2026-09-01": "y"}
```

Test determinizmu jest kluczowy — zabezpieczenie „commit tylko przy realnej zmianie" na GHA porównuje
bajty pliku.

- [ ] **Step 2: Uruchom testy**

Run: `.venv/bin/pytest tests/test_state.py -v`
Expected: FAIL

- [ ] **Step 3: Zaimplementuj**

```python
import json
from pathlib import Path

from ccdrop.models import State, WatchState

FILENAME = "seen.json"
VERSION = 1


def load_state(state_dir: Path) -> State:
    path = Path(state_dir) / FILENAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return State()

    watch = {
        key: WatchState(warm=bool(v.get("warm")), seen_events=dict(v.get("seen_events", {})))
        for key, v in raw.get("watch_state", {}).items()
    }
    return State(
        watch_state=watch,
        http_cache=dict(raw.get("http_cache", {})),
        cinema_names=dict(raw.get("cinema_names", {})),
    )


def serialize(state: State) -> str:
    payload = {
        "version": VERSION,
        "watch_state": {
            key: {"warm": v.warm, "seen_events": v.seen_events}
            for key, v in state.watch_state.items()
        },
        "http_cache": state.http_cache,
        "cinema_names": state.cinema_names,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def save_state(state_dir: Path, state: State) -> None:
    directory = Path(state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / FILENAME
    tmp = directory / f"{FILENAME}.tmp"
    tmp.write_text(serialize(state), encoding="utf-8")
    tmp.replace(target)


def prune(state: State, today: str) -> State:
    watch = {
        key: WatchState(
            warm=v.warm,
            seen_events={eid: day for eid, day in v.seen_events.items() if day >= today},
        )
        for key, v in state.watch_state.items()
    }
    cache = {key: lm for key, lm in state.http_cache.items() if key.split("|", 1)[1] >= today}
    return State(watch_state=watch, http_cache=cache, cinema_names=dict(state.cinema_names))
```

Daty w formacie `YYYY-MM-DD` porównują się poprawnie leksykograficznie, więc parsowanie jest zbędne.
`tmp.replace(target)` to atomowa podmiana — przerwany proces nie zostawi uszkodzonego JSON-a.

- [ ] **Step 4: Uruchom testy**

Run: `.venv/bin/pytest tests/test_state.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add ccdrop/state.py tests/test_state.py
git commit -m "feat: add state persistence with deterministic serialization"
```

---

## Task 7: Rdzeń — wykrywanie zimnych kin

**Files:**
- Create: `ccdrop/detector.py`
- Test: `tests/test_detector_cold_cinemas.py`

`cold_cinemas()` musi działać **przed** pobieraniem, bo decyduje, czy wysłać warunkowy GET.

- [ ] **Step 1: Napisz failujące testy**

```python
from ccdrop.detector import cold_cinemas
from ccdrop.models import Config, WatchEntry, WatchState


def config_with(*entries, cinemas=("1090", "1064")):
    return Config(horizon_days=90, cinemas=cinemas, watch=entries)


def test_unknown_key_counts_as_cold():
    config = config_with(WatchEntry(match="A"))

    assert cold_cinemas(config, {}) == {"1090", "1064"}


def test_warm_pair_is_not_cold():
    config = config_with(WatchEntry(match="A"), cinemas=("1090",))
    state = {"A|1090": WatchState(warm=True)}

    assert cold_cinemas(config, state) == set()


def test_explicitly_cold_pair_is_cold():
    config = config_with(WatchEntry(match="A"), cinemas=("1090",))
    state = {"A|1090": WatchState(warm=False)}

    assert cold_cinemas(config, state) == {"1090"}


def test_entry_scoped_cinemas_limit_the_result():
    config = config_with(WatchEntry(match="A", cinemas=("1090",)))

    assert cold_cinemas(config, {}) == {"1090"}
```

- [ ] **Step 2: Uruchom testy**

Run: `.venv/bin/pytest tests/test_detector_cold_cinemas.py -v`
Expected: FAIL

- [ ] **Step 3: Zaimplementuj**

```python
from ccdrop.models import Config, WatchEntry, WatchState


def watch_key(entry: WatchEntry, cinema_id: str) -> str:
    return f"{entry.match}|{cinema_id}"


def entry_cinemas(config: Config, entry: WatchEntry) -> tuple[str, ...]:
    return entry.cinemas or config.cinemas


def cold_cinemas(config: Config, watch_state: dict[str, WatchState]) -> set[str]:
    cold = set()
    for entry in config.watch:
        for cinema_id in entry_cinemas(config, entry):
            state = watch_state.get(watch_key(entry, cinema_id))
            if state is None or not state.warm:
                cold.add(cinema_id)
    return cold
```

- [ ] **Step 4: Uruchom testy**

Run: `.venv/bin/pytest tests/test_detector_cold_cinemas.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add ccdrop/detector.py tests/test_detector_cold_cinemas.py
git commit -m "feat: detect cinemas needing unconditional fetch"
```

---

## Task 8: Rdzeń — zimny start i diff

**Files:**
- Modify: `ccdrop/detector.py`
- Test: `tests/test_detector_detect.py`

To najważniejsze zadanie w całym planie. Sygnatura:

```
detect(config, watch_state, fetched_events, complete_cinemas, force_match=None) -> DetectResult
```

`DetectResult` niesie `drops` (do wysłania) oraz `baselines` (do zapisania **bez** wysyłania).

- [ ] **Step 1: Napisz failujące testy**

```python
from ccdrop.detector import detect
from ccdrop.models import Config, Event, WatchEntry, WatchState


def event(eid, name="Backrooms. Bez wyjścia", cinema="1090", day="2026-08-15"):
    return Event(
        id=eid,
        film_id="f1",
        film_name=name,
        cinema_id=cinema,
        business_day=day,
        date_time=f"{day}T18:30:00",
        auditorium="Sala 4",
        booking_link=f"https://tickets.cinema-city.pl/api/order/{eid}",
        attribute_ids=("imax",),
    )


CONFIG = Config(horizon_days=90, cinemas=("1090",), watch=(WatchEntry(match="Backrooms"),))


def test_cold_start_sends_nothing():
    result = detect(CONFIG, {}, [event("1")], {"1090"})

    assert result.drops == ()


def test_cold_start_records_baseline():
    result = detect(CONFIG, {}, [event("1")], {"1090"})

    assert result.baselines == {"Backrooms|1090": {"1": "2026-08-15"}}


def test_cinema_without_dates_list_stays_cold():
    result = detect(CONFIG, {}, [event("1")], set())

    assert result.baselines == {}


def test_warm_pair_reports_new_event():
    state = {"Backrooms|1090": WatchState(warm=True, seen_events={})}
    result = detect(CONFIG, state, [event("1")], set())

    assert result.drops[0].events[0].id == "1"


def test_known_event_is_not_reported():
    state = {"Backrooms|1090": WatchState(warm=True, seen_events={"1": "2026-08-15"})}
    result = detect(CONFIG, state, [event("1")], set())

    assert result.drops == ()


def test_unmatched_film_is_ignored():
    state = {"Backrooms|1090": WatchState(warm=True, seen_events={})}
    result = detect(CONFIG, state, [event("1", name="Diuna 3")], set())

    assert result.drops == ()


def test_events_are_grouped_per_film():
    state = {"Backrooms|1090": WatchState(warm=True, seen_events={})}
    events = [event("1"), event("2", name="Backrooms. Wersja rozszerzona")]
    result = detect(CONFIG, state, events, set())

    assert len(result.drops) == 2


def test_force_match_reports_already_seen_event():
    state = {"Backrooms|1090": WatchState(warm=True, seen_events={"1": "2026-08-15"})}
    result = detect(CONFIG, state, [event("1")], set(), force_match="Backrooms")

    assert result.drops[0].events[0].id == "1"


def test_adding_cinema_cold_starts_only_new_pair():
    config = Config(horizon_days=90, cinemas=("1090", "1064"), watch=(WatchEntry(match="Backrooms"),))
    state = {"Backrooms|1090": WatchState(warm=True, seen_events={})}
    events = [event("1"), event("2", cinema="1064")]
    result = detect(config, state, events, {"1090", "1064"})

    assert set(result.baselines) == {"Backrooms|1064"}
```

Kompromis ze specyfikacji — kompletność zależy od pobrania **listy dat**, a nie wszystkich dat —
jest sprawdzany na poziomie `run_cycle` w zadaniu 13, bo dopiero tam istnieje pojęcie daty, która
zawiodła. Próba przetestowania go tutaj daje asercję o ID, którego w wejściu nie ma, czyli test
niezdolny do porażki.

- [ ] **Step 2: Uruchom testy**

Run: `.venv/bin/pytest tests/test_detector_detect.py -v`
Expected: FAIL

- [ ] **Step 3: Zaimplementuj**

Dopisz do `ccdrop/detector.py`:

```python
from collections import defaultdict
from dataclasses import dataclass

from ccdrop.matching import matches
from ccdrop.models import Config, Drop, Event, WatchState


@dataclass(frozen=True)
class DetectResult:
    drops: tuple[Drop, ...]
    baselines: dict[str, dict[str, str]]


def detect(
    config: Config,
    watch_state: dict[str, WatchState],
    fetched_events: list[Event],
    complete_cinemas: set[str],
    force_match: str | None = None,
) -> DetectResult:
    drops: list[Drop] = []
    baselines: dict[str, dict[str, str]] = {}

    for entry in config.watch:
        for cinema_id in entry_cinemas(config, entry):
            key = watch_key(entry, cinema_id)
            state = watch_state.get(key)
            matched = [
                e
                for e in fetched_events
                if e.cinema_id == cinema_id and matches(entry.match, e.film_name)
            ]

            if state is None or not state.warm:
                if cinema_id in complete_cinemas:
                    baselines[key] = {e.id: e.business_day for e in matched}
                continue

            seen = {} if entry.match == force_match else state.seen_events
            fresh = [e for e in matched if e.id not in seen]
            by_film: dict[str, list[Event]] = defaultdict(list)
            for e in fresh:
                by_film[e.film_name].append(e)

            for film_name in sorted(by_film):
                group = sorted(by_film[film_name], key=lambda e: e.date_time)
                drops.append(
                    Drop(
                        watch_key=key,
                        film_name=film_name,
                        cinema_id=cinema_id,
                        events=tuple(group),
                    )
                )

    return DetectResult(drops=tuple(drops), baselines=baselines)
```

Sortowanie po nazwie filmu i po godzinie zapewnia powtarzalną kolejność wiadomości — bez tego testy
byłyby zależne od kolejności iteracji.

- [ ] **Step 4: Uruchom testy**

Run: `.venv/bin/pytest tests/test_detector_detect.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add ccdrop/detector.py tests/test_detector_detect.py
git commit -m "feat: add cold start and drop detection core"
```

---

## Task 9: Klient API — budowa URL-i i parsowanie

**Files:**
- Create: `ccdrop/api.py`, `tests/fixtures/film_events_1090.json`
- Test: `tests/test_api_parsing.py`

- [ ] **Step 1: Pobierz prawdziwą odpowiedź jako fixture**

```bash
mkdir -p tests/fixtures
curl -s "https://www.cinema-city.pl/pl/data-api-service/v1/quickbook/10103/film-events/in-cinema/1090/at-date/$(date -v+2d +%F)?attr=&lang=pl_PL" \
  > tests/fixtures/film_events_1090.json
```

Sprawdź, że plik ma niepustą tablicę `events` — jeśli kino akurat nie gra, weź inną datę.

- [ ] **Step 2: Napisz failujące testy**

```python
import json
from pathlib import Path

from ccdrop.api import events_url, parse_film_events

FIXTURE = Path(__file__).parent / "fixtures" / "film_events_1090.json"


def test_events_url_contains_cinema_and_date():
    url = events_url("1090", "2026-08-15")

    assert "/film-events/in-cinema/1090/at-date/2026-08-15" in url


def test_parses_all_events():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert len(parse_film_events(payload)) == len(payload["body"]["events"])


def test_joins_film_name_from_films_list():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    first = parse_film_events(payload)[0]
    expected = next(f["name"] for f in payload["body"]["films"] if f["id"] == first.film_id)

    assert first.film_name == expected


def test_skips_event_with_unknown_film():
    payload = {"body": {"films": [], "events": [{"id": "1", "filmId": "brak"}]}}

    assert parse_film_events(payload) == []
```

Ostatni test realizuje wymóg ze specyfikacji: zmiana kształtu odpowiedzi pomija pojedynczy event,
zamiast wywracać cały cykl.

- [ ] **Step 3: Uruchom testy**

Run: `.venv/bin/pytest tests/test_api_parsing.py -v`
Expected: FAIL

- [ ] **Step 4: Zaimplementuj**

```python
from ccdrop.models import Event

BASE = "https://www.cinema-city.pl/pl/data-api-service/v1/quickbook/10103"
QUERY = "?attr=&lang=pl_PL"


def cinemas_url(until: str) -> str:
    return f"{BASE}/cinemas/with-event/until/{until}{QUERY}"


def dates_url(cinema_id: str, until: str) -> str:
    return f"{BASE}/dates/in-cinema/{cinema_id}/until/{until}{QUERY}"


def events_url(cinema_id: str, date: str) -> str:
    return f"{BASE}/film-events/in-cinema/{cinema_id}/at-date/{date}{QUERY}"


def parse_film_events(payload: dict) -> list[Event]:
    body = payload.get("body", {})
    names = {f["id"]: f["name"] for f in body.get("films", [])}
    events = []
    for raw in body.get("events", []):
        film_id = raw.get("filmId")
        if film_id not in names:
            continue
        try:
            events.append(
                Event(
                    id=str(raw["id"]),
                    film_id=film_id,
                    film_name=names[film_id],
                    cinema_id=str(raw["cinemaId"]),
                    business_day=raw["businessDay"],
                    date_time=raw["eventDateTime"],
                    auditorium=raw.get("auditorium", ""),
                    booking_link=raw.get("bookingLink", ""),
                    attribute_ids=tuple(raw.get("attributeIds", [])),
                )
            )
        except KeyError:
            continue
    return events


def parse_dates(payload: dict) -> list[str]:
    return list(payload.get("body", {}).get("dates", []))


def parse_cinema_names(payload: dict) -> dict[str, str]:
    return {str(c["id"]): c["displayName"] for c in payload.get("body", {}).get("cinemas", [])}
```

- [ ] **Step 5: Uruchom testy**

Run: `.venv/bin/pytest tests/test_api_parsing.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add ccdrop/api.py tests/test_api_parsing.py tests/fixtures
git commit -m "feat: add Cinema City API urls and parsing"
```

---

## Task 10: Klient API — warunkowe GET-y, backoff, throttle

**Files:**
- Modify: `ccdrop/api.py`
- Test: `tests/test_api_client.py`

- [ ] **Step 1: Napisz failujące testy**

Użyj podstawionej sesji zamiast prawdziwej sieci.

```python
import pytest

from ccdrop.api import FetchOutcome, ApiClient


class FakeResponse:
    def __init__(self, status_code, headers=None, payload=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, dict(headers or {})))
        return self.responses.pop(0)


def client(session):
    return ApiClient(session=session, sleep=lambda _: None)


def test_sends_if_modified_since_when_cached():
    session = FakeSession([FakeResponse(304)])
    client(session).fetch("http://x", last_modified="Sat, 01 Aug 2026 21:07:38 GMT")

    assert session.calls[0][1]["If-Modified-Since"] == "Sat, 01 Aug 2026 21:07:38 GMT"


def test_omits_header_without_cache():
    session = FakeSession([FakeResponse(200, {"Last-Modified": "x"}, {"body": {}})])
    client(session).fetch("http://x", last_modified=None)

    assert "If-Modified-Since" not in session.calls[0][1]


def test_304_reports_not_modified():
    session = FakeSession([FakeResponse(304)])

    assert client(session).fetch("http://x", "lm").status is FetchOutcome.NOT_MODIFIED


def test_200_returns_payload():
    session = FakeSession([FakeResponse(200, {"Last-Modified": "x"}, {"body": {"a": 1}})])

    assert client(session).fetch("http://x", None).payload == {"body": {"a": 1}}


def test_retries_on_429_then_succeeds():
    session = FakeSession(
        [FakeResponse(429), FakeResponse(200, {"Last-Modified": "x"}, {"body": {}})]
    )

    assert client(session).fetch("http://x", None).status is FetchOutcome.OK


def test_gives_up_after_three_attempts():
    session = FakeSession([FakeResponse(500), FakeResponse(500), FakeResponse(500)])

    assert client(session).fetch("http://x", None).status is FetchOutcome.FAILED
```

- [ ] **Step 2: Uruchom testy**

Run: `.venv/bin/pytest tests/test_api_client.py -v`
Expected: FAIL

- [ ] **Step 3: Zaimplementuj**

```python
import time
from dataclasses import dataclass
from enum import Enum

import requests

USER_AGENT = "ccdrop/0.1 (+https://github.com/Laaidback/cinema-city-drop-detector)"
MAX_ATTEMPTS = 3
THROTTLE_SECONDS = 0.2


class FetchOutcome(Enum):
    OK = "ok"
    NOT_MODIFIED = "not_modified"
    FAILED = "failed"


@dataclass(frozen=True)
class FetchResult:
    status: FetchOutcome
    payload: dict | None = None
    last_modified: str | None = None


class ApiClient:
    def __init__(self, session=None, sleep=time.sleep):
        self.session = session or requests.Session()
        self.sleep = sleep

    def fetch(self, url: str, last_modified: str | None) -> FetchResult:
        headers = {"User-Agent": USER_AGENT}
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self.session.get(url, headers=headers, timeout=30)
            except requests.RequestException:
                self.sleep(2**attempt)
                continue

            if response.status_code == 304:
                return FetchResult(FetchOutcome.NOT_MODIFIED)
            if response.status_code == 200:
                return FetchResult(
                    FetchOutcome.OK,
                    payload=response.json(),
                    last_modified=response.headers.get("Last-Modified"),
                )
            if response.status_code == 429 or response.status_code >= 500:
                self.sleep(2**attempt)
                continue
            return FetchResult(FetchOutcome.FAILED)

        return FetchResult(FetchOutcome.FAILED)

    def throttle(self) -> None:
        self.sleep(THROTTLE_SECONDS)
```

- [ ] **Step 3a: Dopisz adapter `CinemaCityApi`**

To powierzchnia, której używa `run_cycle` i którą atrapują testy zadania 13. Musi być kodem, nie
opisem — od zgodności sygnatur zależy, czy testy zadania 13 w ogóle zagrają.

```python
import logging

log = logging.getLogger("ccdrop")


class CinemaCityApi:
    def __init__(self, client: ApiClient):
        self.client = client

    def fetch_cinema_names(self, until: str) -> dict[str, str]:
        result = self.client.fetch(cinemas_url(until), None)
        self.client.throttle()
        if result.status is not FetchOutcome.OK:
            log.warning("Nie udało się pobrać nazw kin — powiadomienia pokażą numery")
            return {}
        return parse_cinema_names(result.payload)

    def fetch_dates(self, cinema_id: str, until: str) -> list[str] | None:
        result = self.client.fetch(dates_url(cinema_id, until), None)
        self.client.throttle()
        if result.status is not FetchOutcome.OK:
            log.warning("Brak listy dat dla kina %s — kino pominięte w tym cyklu", cinema_id)
            return None
        return parse_dates(result.payload)

    def fetch_events(self, cinema_id: str, day: str, last_modified: str | None):
        result = self.client.fetch(events_url(cinema_id, day), last_modified)
        self.client.throttle()
        log.debug("kino %s dzień %s -> %s", cinema_id, day, result.status.value)
        return result
```

Throttle jest wołany **tutaj**, po każdym żądaniu — inaczej `ApiClient.throttle()` nie miałby ani
jednego miejsca wywołania i wymóg 200 ms wypadłby z implementacji. `fetch_cinema_names` zwraca `{}`
zamiast rzucać, bo specyfikacja wymaga, by powiadomienie wyszło choćby z samym numerem kina.

Dopisz też logowanie kodu HTTP w `ApiClient.fetch`, zaraz po otrzymaniu odpowiedzi:

```python
            log.debug("%s -> HTTP %s", url, response.status_code)
```

Enum `ok/not_modified/failed` nie odróżnia `403` od `500`, a przy diagnozie to najważniejsza
informacja.

- [ ] **Step 3b: Testy adaptera**

`tests/test_api_adapter.py` — kontrakt zwracania `None`/`{}` przy błędzie jest inaczej sprawdzany
dopiero w weryfikacji end-to-end.

```python
from ccdrop.api import CinemaCityApi, FetchOutcome, FetchResult


class StubClient:
    def __init__(self, result):
        self.result = result

    def fetch(self, url, last_modified):
        return self.result

    def throttle(self):
        pass


def test_dates_failure_returns_none():
    api = CinemaCityApi(StubClient(FetchResult(FetchOutcome.FAILED)))

    assert api.fetch_dates("1090", "2026-09-01") is None


def test_dates_success_returns_list():
    payload = {"body": {"dates": ["2026-08-15"]}}
    api = CinemaCityApi(StubClient(FetchResult(FetchOutcome.OK, payload=payload)))

    assert api.fetch_dates("1090", "2026-09-01") == ["2026-08-15"]


def test_cinema_names_failure_returns_empty_dict():
    api = CinemaCityApi(StubClient(FetchResult(FetchOutcome.FAILED)))

    assert api.fetch_cinema_names("2026-09-01") == {}
```

Run: `.venv/bin/pytest tests/test_api_adapter.py -v`
Expected: 3 passed

- [ ] **Step 4: Uruchom testy**

Run: `.venv/bin/pytest tests/test_api_client.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add ccdrop/api.py tests/test_api_client.py tests/test_api_adapter.py
git commit -m "feat: add conditional fetching with backoff"
```

---

## Task 11: Formatowanie powiadomień

**Files:**
- Create: `ccdrop/notifier.py`
- Test: `tests/test_notifier_format.py`

- [ ] **Step 1: Napisz failujące testy**

```python
from ccdrop.models import Drop, Event
from ccdrop.notifier import format_drop, plural_screenings


def event(eid, day="2026-08-15", time="18:30", attrs=("imax",)):
    return Event(
        id=eid,
        film_id="f1",
        film_name="Backrooms. Bez wyjścia",
        cinema_id="1090",
        business_day=day,
        date_time=f"{day}T{time}:00",
        auditorium="Sala 4",
        booking_link=f"https://tickets.cinema-city.pl/api/order/{eid}",
        attribute_ids=attrs,
    )


def drop_with(events):
    return Drop(
        watch_key="Backrooms|1090",
        film_name="Backrooms. Bez wyjścia",
        cinema_id="1090",
        events=tuple(events),
    )


def test_singular_form():
    assert plural_screenings(1) == "1 nowy seans"


def test_few_form():
    assert plural_screenings(3) == "3 nowe seanse"


def test_many_form():
    assert plural_screenings(6) == "6 nowych seansów"


def test_teens_take_genitive():
    assert plural_screenings(13) == "13 nowych seansów"


def test_header_uses_cinema_name():
    text = format_drop(drop_with([event("1")]), {"1090": "Kraków Bonarka"})

    assert "Kraków Bonarka" in text


def test_header_falls_back_to_cinema_id():
    text = format_drop(drop_with([event("1")]), {})

    assert "1090" in text


def test_known_attribute_is_labelled():
    text = format_drop(drop_with([event("1", attrs=("dolby-cinema",))]), {})

    assert "Dolby Cinema" in text


def test_unknown_attribute_is_dropped():
    text = format_drop(drop_with([event("1", attrs=("subbed",))]), {})

    assert "subbed" not in text


def test_weekday_is_polish_abbreviation():
    text = format_drop(drop_with([event("1", day="2026-08-15")]), {})

    assert "sb 15.08" in text


def test_list_is_truncated_after_fifteen():
    events = [event(str(i), time=f"{i % 24:02d}:00") for i in range(20)]
    text = format_drop(drop_with(events), {})

    assert "…i 5 więcej" in text
```

`2026-08-15` to sobota — sprawdź kalendarz, jeśli zmieniasz datę w teście.

- [ ] **Step 2: Uruchom testy**

Run: `.venv/bin/pytest tests/test_notifier_format.py -v`
Expected: FAIL

- [ ] **Step 3: Zaimplementuj formatowanie**

```python
from datetime import datetime

from ccdrop.models import Drop

MAX_ROWS = 15
WEEKDAYS = ("pn", "wt", "śr", "cz", "pt", "sb", "nd")
ATTRIBUTE_LABELS = {
    "imax": "IMAX",
    "4dx": "4DX",
    "screenx": "ScreenX",
    "dolby-cinema": "Dolby Cinema",
    "vip": "VIP",
    "3d": "3D",
}


def plural_screenings(count: int) -> str:
    if count == 1:
        return "1 nowy seans"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return f"{count} nowe seanse"
    return f"{count} nowych seansów"


def format_drop(drop: Drop, cinema_names: dict[str, str]) -> str:
    cinema = cinema_names.get(drop.cinema_id, drop.cinema_id)
    lines = [
        f"🎬 {drop.film_name}",
        f"📍 {cinema} · {plural_screenings(len(drop.events))}",
        "",
    ]

    for event in drop.events[:MAX_ROWS]:
        moment = datetime.fromisoformat(event.date_time)
        stamp = f"{WEEKDAYS[moment.weekday()]} {moment:%d.%m}  {moment:%H:%M}"
        labels = [ATTRIBUTE_LABELS[a] for a in event.attribute_ids if a in ATTRIBUTE_LABELS]
        room = " · ".join([event.auditorium, *labels])
        lines.append(f"  {stamp}  {room}  {event.booking_link}")

    hidden = len(drop.events) - MAX_ROWS
    if hidden > 0:
        lines.append(f"  …i {hidden} więcej")

    return "\n".join(lines)
```

Czasy w `eventDateTime` są już lokalne dla kina, więc `fromisoformat` wystarcza — konwersja stref
byłaby błędem. Strefa Europe/Warsaw ma znaczenie wyłącznie przy liczeniu „dziś" (zadanie 13).

- [ ] **Step 4: Uruchom testy**

Run: `.venv/bin/pytest tests/test_notifier_format.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add ccdrop/notifier.py tests/test_notifier_format.py
git commit -m "feat: add Telegram message formatting"
```

---

## Task 12: Wysyłka na Telegram

**Files:**
- Modify: `ccdrop/notifier.py`
- Test: `tests/test_notifier_send.py`

- [ ] **Step 1: Napisz failujące testy**

```python
from ccdrop.notifier import TelegramNotifier


class FakeResponse:
    def __init__(self, ok):
        self.status_code = 200 if ok else 500


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        return self.responses.pop(0)


def test_successful_send_reports_true():
    session = FakeSession([FakeResponse(True)])

    assert TelegramNotifier("tok", "42", session).send("treść") is True


def test_failed_send_reports_false():
    session = FakeSession([FakeResponse(False)])

    assert TelegramNotifier("tok", "42", session).send("treść") is False


def test_posts_to_chat_id():
    session = FakeSession([FakeResponse(True)])
    TelegramNotifier("tok", "42", session).send("treść")

    assert session.calls[0][1]["chat_id"] == "42"
```

Wysyłka zwraca `bool`, a nie rzuca wyjątkiem — `main` musi rozróżnić grupy dostarczone od
niedostarczonych, bo od tego zależy, co wolno utrwalić.

- [ ] **Step 2: Uruchom testy**

Run: `.venv/bin/pytest tests/test_notifier_send.py -v`
Expected: FAIL

- [ ] **Step 3: Zaimplementuj**

```python
import requests


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, session=None):
        self.token = token
        self.chat_id = chat_id
        self.session = session or requests.Session()

    def send(self, text: str) -> bool:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}
        try:
            response = self.session.post(url, json=payload, timeout=30)
        except requests.RequestException:
            return False
        return response.status_code == 200
```

- [ ] **Step 4: Uruchom testy**

Run: `.venv/bin/pytest tests/test_notifier_send.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add ccdrop/notifier.py tests/test_notifier_send.py
git commit -m "feat: add Telegram delivery"
```

---

## Task 13: Przepływ cyklu i reguły utrwalania

**Files:**
- Create: `ccdrop/main.py`
- Test: `tests/test_main_persistence.py`

Najbardziej podatna na błąd część projektu. Zaimplementuj dokładnie tabelę ze specyfikacji.

- [ ] **Step 1: Napisz failujące testy**

Wstrzyknij atrapy klienta API i notifiera, żeby testy nie dotykały sieci.

```python
from ccdrop.main import run_cycle
from ccdrop.models import Config, State, WatchEntry, WatchState

CONFIG = Config(horizon_days=90, cinemas=("1090",), watch=(WatchEntry(match="Backrooms"),))


def test_failed_send_does_not_record_seen_events(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=False)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert state.watch_state["Backrooms|1090"].seen_events == {}


def test_successful_send_records_seen_events(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert state.watch_state["Backrooms|1090"].seen_events == {"1": "2026-08-15"}


def test_failed_send_blocks_all_http_cache_updates(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=False)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert state.http_cache == {}


def test_failed_fetch_removes_cache_entry(fake_world):
    world = fake_world(warm=True, events=[], failed_dates=["2026-08-15"])
    world.state.http_cache["1090|2026-08-15"] = "stary"
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert "1090|2026-08-15" not in state.http_cache


def test_cold_pair_warms_without_sending(fake_world):
    world = fake_world(warm=False, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert world.notifier.sent == []


def test_cold_pair_forces_unconditional_fetch(fake_world):
    world = fake_world(warm=False, events=[("1", "2026-08-15")])
    world.state.http_cache["1090|2026-08-15"] = "stary"
    run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert world.api.conditional_calls == []


def test_dates_failure_leaves_pairs_cold(fake_world):
    world = fake_world(warm=False, events=[], dates_fail=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert state.watch_state.get("Backrooms|1090") is None


def test_dry_run_records_no_seen_events(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, "2026-08-02", dry_run=True)

    assert state.watch_state["Backrooms|1090"].seen_events == {}


def test_dry_run_records_no_http_cache(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, "2026-08-02", dry_run=True)

    assert state.http_cache == {}


def test_dry_run_does_not_warm_cold_pair(fake_world):
    world = fake_world(warm=False, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, "2026-08-02", dry_run=True)

    assert state.watch_state == {}


def test_dry_run_sends_nothing(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    run_cycle(CONFIG, world.state, world.api, world.notifier, "2026-08-02", dry_run=True)

    assert world.notifier.sent == []
```

- [ ] **Step 1a: Napisz `tests/conftest.py`**

Kod wprost, bo z samych testów nie da się go jednoznacznie wyprowadzić. Krytyczne szczegóły:
`fetch_events` zwraca **surowy payload API** w camelCase (bo `run_cycle` woła na nim
`parse_film_events`), `fetch_dates` scala dni z eventów i dni błędnych, a `last_modified` musi być
niepuste — inaczej `test_failed_send_blocks_all_http_cache_updates` przechodziłby **pusto**,
niezależnie od tego, czy reguła jest zaimplementowana.

```python
import dataclasses

import pytest

from ccdrop.api import FetchOutcome, FetchResult
from ccdrop.models import State, WatchState


class FakeApi:
    def __init__(self, events_by_date, failed_dates, dates_fail):
        self.events_by_date = events_by_date
        self.failed_dates = set(failed_dates)
        self.dates_fail = dates_fail
        self.conditional_calls = []

    def fetch_cinema_names(self, until):
        return {"1090": "Kraków Bonarka"}

    def fetch_dates(self, cinema_id, until):
        if self.dates_fail:
            return None
        return sorted(set(self.events_by_date) | self.failed_dates)

    def fetch_events(self, cinema_id, day, last_modified):
        if last_modified is not None:
            self.conditional_calls.append((cinema_id, day))
        if day in self.failed_dates:
            return FetchResult(FetchOutcome.FAILED)
        raw = [
            {
                "id": eid,
                "filmId": "f1",
                "cinemaId": cinema_id,
                "businessDay": business_day,
                "eventDateTime": f"{business_day}T18:30:00",
                "auditorium": "Sala 4",
                "bookingLink": f"https://tickets.cinema-city.pl/api/order/{eid}",
                "attributeIds": ["imax"],
            }
            for eid, business_day in self.events_by_date.get(day, [])
        ]
        payload = {
            "body": {"films": [{"id": "f1", "name": "Backrooms. Bez wyjścia"}], "events": raw}
        }
        return FetchResult(FetchOutcome.OK, payload=payload, last_modified="LM")


class FakeNotifier:
    def __init__(self, ok):
        self.ok = ok
        self.sent = []

    def send(self, text):
        self.sent.append(text)
        return self.ok


@dataclasses.dataclass
class World:
    state: State
    api: FakeApi
    notifier: FakeNotifier


@pytest.fixture
def fake_world():
    def build(warm, events=(), send_ok=True, failed_dates=(), dates_fail=False):
        events_by_date = {}
        for event_id, business_day in events:
            events_by_date.setdefault(business_day, []).append((event_id, business_day))
        state = State()
        if warm:
            state.watch_state["Backrooms|1090"] = WatchState(warm=True, seen_events={})
        return World(
            state=state,
            api=FakeApi(events_by_date, failed_dates, dates_fail),
            notifier=FakeNotifier(send_ok),
        )

    return build
```

`warm=False` daje **pusty** `watch_state`, a nie wpis z `warm: False` — inaczej
`test_dates_failure_leaves_pairs_cold`, który sprawdza `is None`, byłby czerwony.

- [ ] **Step 1b: Dopisz dwa brakujące testy**

```python
def test_existing_seen_events_survive_new_drop(fake_world):
    world = fake_world(warm=True, events=[("2", "2026-08-16")], send_ok=True)
    world.state.watch_state["Backrooms|1090"].seen_events["1"] = "2026-08-15"
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert "1" in state.watch_state["Backrooms|1090"].seen_events


def test_repeat_after_failed_send_delivers_again(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=False)
    after_failure = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")
    world.notifier.ok = True
    run_cycle(CONFIG, after_failure, world.api, world.notifier, today="2026-08-02")

    assert len(world.notifier.sent) == 2


def test_pair_warms_despite_failing_date(fake_world):
    world = fake_world(warm=False, events=[("1", "2026-08-15")], failed_dates=["2026-08-16"])
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert state.watch_state["Backrooms|1090"].warm is True


def test_failing_date_leaves_no_cache_entry(fake_world):
    world = fake_world(warm=False, events=[("1", "2026-08-15")], failed_dates=["2026-08-16"])
    world.state.http_cache["1090|2026-08-16"] = "stary"
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert "1090|2026-08-16" not in state.http_cache


def test_force_send_bypasses_conditional_fetch(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    world.state.http_cache["1090|2026-08-15"] = "stary"
    run_cycle(CONFIG, world.state, world.api, world.notifier, "2026-08-02", force_match="Backrooms")

    assert world.api.conditional_calls == []


def test_force_send_keeps_existing_seen_events(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    world.state.watch_state["Backrooms|1090"].seen_events["9"] = "2026-08-20"
    state = run_cycle(
        CONFIG, world.state, world.api, world.notifier, "2026-08-02", force_match="Backrooms"
    )

    assert "9" in state.watch_state["Backrooms|1090"].seen_events
```

`test_repeat_after_failed_send_delivers_again` przekazuje stan zwrócony przez pierwszy cykl do
drugiego — inaczej sprawdzałby tylko, że dwa niezależne cykle robią to samo, a nie własność
at-least-once.

Dwa testy `force_send` są konieczne, bo ta ścieżka raz już cicho zregresowała. Bez nich usunięcie
dowolnej z dwóch linii obsługujących `force_match` zostawia cały zestaw zielony.

`test_pair_warms_despite_failing_date` to jedyne realne pokrycie wymogu „para z trwale błędną datą
ociepla się mimo to". Na poziomie `detect()` nie da się go napisać sensownie.

- [ ] **Step 2: Uruchom testy**

Run: `.venv/bin/pytest tests/test_main_persistence.py -v`
Expected: FAIL

- [ ] **Step 3: Zaimplementuj `run_cycle`**

```python
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ccdrop import api as api_module
from ccdrop.detector import cold_cinemas, detect, entry_cinemas
from ccdrop.models import Config, State, WatchState
from ccdrop.notifier import format_drop

log = logging.getLogger("ccdrop")
WARSAW = ZoneInfo("Europe/Warsaw")


def today_in_warsaw() -> str:
    return datetime.now(WARSAW).date().isoformat()


def horizon_date(today: str, days: int) -> str:
    return (date.fromisoformat(today) + timedelta(days=days)).isoformat()


def run_cycle(config, state, api, notifier, today, dry_run=False, force_match=None):
    until = horizon_date(today, config.horizon_days)
    cold = cold_cinemas(config, state.watch_state)
    if force_match:
        for entry in config.watch:
            if entry.match == force_match:
                cold.update(entry_cinemas(config, entry))

    names = api.fetch_cinema_names(until)
    cinema_names = {**state.cinema_names, **names}

    fetched_events = []
    complete = set()
    fresh_cache = {}
    dropped_cache = []

    for cinema_id in config.cinemas:
        dates = api.fetch_dates(cinema_id, until)
        if dates is None:
            continue
        complete.add(cinema_id)
        for day in dates:
            key = f"{cinema_id}|{day}"
            cached = None if cinema_id in cold else state.http_cache.get(key)
            result = api.fetch_events(cinema_id, day, cached)
            if result.status is api_module.FetchOutcome.FAILED:
                dropped_cache.append(key)
                continue
            if result.status is api_module.FetchOutcome.NOT_MODIFIED:
                continue
            fetched_events.extend(api_module.parse_film_events(result.payload))
            if result.last_modified:
                fresh_cache[key] = result.last_modified

    outcome = detect(config, state.watch_state, fetched_events, complete, force_match)
    log.info("Pobrano %d seansów, wykryto %d grup", len(fetched_events), len(outcome.drops))

    send_failed = False
    delivered: dict[str, dict[str, str]] = {}
    for drop in outcome.drops:
        text = format_drop(drop, cinema_names)
        if dry_run:
            print(text)
            print()
            continue
        if notifier.send(text):
            delivered.setdefault(drop.watch_key, {}).update(
                {e.id: e.business_day for e in drop.events}
            )
        else:
            send_failed = True

    if dry_run:
        return state

    new_watch = dict(state.watch_state)
    for key, events in delivered.items():
        current = new_watch.get(key, WatchState())
        merged = {**current.seen_events, **events}
        new_watch[key] = WatchState(warm=True, seen_events=merged)
    for key, baseline in outcome.baselines.items():
        new_watch[key] = WatchState(warm=True, seen_events=dict(baseline))

    new_cache = dict(state.http_cache)
    if not send_failed:
        new_cache.update(fresh_cache)
    for key in dropped_cache:
        new_cache.pop(key, None)

    return State(watch_state=new_watch, http_cache=new_cache, cinema_names=cinema_names)
```

Trzy rzeczy, których nie wolno pomylić: usuwanie wpisu przy nieudanym pobraniu dzieje się **zawsze**,
także gdy wysyłka zawiodła (usunięcie jest bezpieczne w tę stronę); `fresh_cache` jest aplikowany
wyłącznie przy braku porażek wysyłki; `dry_run` zwraca stan wejściowy nietknięty.

- [ ] **Step 4: Uruchom testy**

Run: `.venv/bin/pytest tests/test_main_persistence.py -v`
Expected: 17 passed

- [ ] **Step 5: Uruchom cały zestaw**

Run: `.venv/bin/pytest -v`
Expected: wszystko zielone

- [ ] **Step 6: Commit**

```bash
git add ccdrop/main.py tests/test_main_persistence.py tests/conftest.py
git commit -m "feat: add cycle orchestration and persistence rules"
```

---

## Task 14: Interfejs wiersza poleceń

**Files:**
- Modify: `ccdrop/main.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Napisz failujący test**

```python
from ccdrop.main import parse_args


def test_dry_run_defaults_to_false():
    assert parse_args([]).dry_run is False


def test_state_dir_has_default():
    assert parse_args([]).state_dir.name == "state"


def test_force_send_takes_match_value():
    assert parse_args(["--force-send", "Backrooms"]).force_send == "Backrooms"
```

- [ ] **Step 2: Uruchom testy**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL

- [ ] **Step 3: Zaimplementuj `parse_args` i `main`**

```python
import argparse
import os
import sys
from pathlib import Path

from ccdrop.api import ApiClient, CinemaCityApi
from ccdrop.config import load_config
from ccdrop.notifier import TelegramNotifier
from ccdrop.state import load_state, prune, save_state


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="ccdrop")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--state-dir", type=Path, default=Path("state"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-send", default=None)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def build_notifier(dry_run: bool):
    if dry_run:
        return None
    try:
        return TelegramNotifier(
            os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
        )
    except KeyError as missing:
        raise SystemExit(f"Brak zmiennej środowiskowej {missing}")


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    logging.getLogger("urllib3").setLevel(logging.INFO)

    config = load_config(args.config)
    if args.force_send and not any(e.match == args.force_send for e in config.watch):
        log.warning("--force-send %s nie pasuje do żadnego wpisu watch", args.force_send)

    state = load_state(args.state_dir)
    today = today_in_warsaw()

    updated = run_cycle(
        config,
        state,
        CinemaCityApi(ApiClient()),
        build_notifier(args.dry_run),
        today,
        dry_run=args.dry_run,
        force_match=args.force_send,
    )

    if not args.dry_run:
        save_state(args.state_dir, prune(updated, today))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Trzy rzeczy, które muszą tu być dokładnie tak:

- **Blok `if __name__ == "__main__"` jest obowiązkowy.** Bez niego `python -m ccdrop.main` tylko
  zaimportuje moduł, wykona definicje i wyjdzie z kodem 0 — każdy przebieg i każdy job w CI byłby
  zielony i całkowicie bezczynny.
- **`--force-send` nie modyfikuje stanu przed cyklem**, tylko jest przekazywany do `run_cycle`.
  Wcześniejsze podmienianie wpisu na `warm=True` z pustym `seen_events` wypychało parę z
  `cold_cinemas`, więc leciał warunkowy GET, wracało `304` i nie było czego wysłać — a pusty
  baseline lądował na dysku i tworzył martwą strefę opisaną w specyfikacji.
- **`--dry-run` nie wymaga tokenu.** Notifier nie powstaje, bo i tak nie jest wołany.

`CinemaCityApi` jest zdefiniowana w zadaniu 10, krok 3a.

Wpisz w `pyproject.toml`:

```toml
[project.scripts]
ccdrop = "ccdrop.main:main"
```

- [ ] **Step 4: Uruchom testy**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add ccdrop/main.py tests/test_cli.py pyproject.toml
git commit -m "feat: add command line interface"
```

---

## Task 15: Skrypty pomocnicze

**Files:**
- Create: `tools/list_cinemas.py`, `tools/get_chat_id.py`

- [ ] **Step 1: Napisz `tools/list_cinemas.py`**

```python
"""Wypisuje numery i nazwy kin Cinema City do wklejenia w config.yaml."""

import sys
from datetime import date, timedelta

import requests

from ccdrop.api import cinemas_url, parse_cinema_names

if __name__ == "__main__":
    needle = sys.argv[1].casefold() if len(sys.argv) > 1 else ""
    until = (date.today() + timedelta(days=30)).isoformat()
    names = parse_cinema_names(requests.get(cinemas_url(until), timeout=30).json())
    for cinema_id, name in sorted(names.items(), key=lambda kv: kv[1]):
        if needle in name.casefold():
            print(f"{cinema_id}  {name}")
```

- [ ] **Step 2: Uruchom i sprawdź**

```bash
.venv/bin/python tools/list_cinemas.py krak
```

Oczekiwane: kilka linii z numerami krakowskich kin. Zapisz numer potrzebnego kina.

- [ ] **Step 3: Napisz `tools/get_chat_id.py`**

```python
"""Wypisuje TELEGRAM_CHAT_ID. Wymaga wcześniejszego napisania czegokolwiek do bota."""

import os
import sys

import requests

if __name__ == "__main__":
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("Ustaw TELEGRAM_BOT_TOKEN przed uruchomieniem")

    updates = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30).json()
    chats = {
        str(u["message"]["chat"]["id"]): u["message"]["chat"].get("first_name", "")
        for u in updates.get("result", [])
        if "message" in u
    }
    if not chats:
        sys.exit("Brak wiadomości. Napisz cokolwiek do swojego bota i spróbuj ponownie.")
    for chat_id, name in chats.items():
        print(f"{chat_id}  {name}")
```

- [ ] **Step 4: Commit**

```bash
git add tools
git commit -m "feat: add helper scripts for cinema ids and chat id"
```

---

## Task 16: Workflow GitHub Actions

**Files:**
- Create: `.github/workflows/check.yml`

- [ ] **Step 1: Napisz workflow**

```yaml
name: check

on:
  schedule:
    - cron: "*/5 * * * *"
  workflow_dispatch:

concurrency:
  group: ccdrop
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - run: pip install -e .

      - name: Pobierz stan
        run: |
          mkdir -p state
          git fetch origin state || true
          git show origin/state:state/seen.json > state/seen.json 2>/dev/null \
            || rm -f state/seen.json

      - name: Uruchom detektor
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python -m ccdrop.main

      - name: Zapisz stan
        run: |
          [ -f state/seen.json ] || { echo "brak stanu do zapisania"; exit 0; }
          git config user.name "ccdrop bot"
          git config user.email "24231775+Laaidback@users.noreply.github.com"
          cp state/seen.json "$RUNNER_TEMP/seen.json"
          for attempt in 1 2 3; do
            git fetch origin state || true
            if git rev-parse --verify origin/state >/dev/null 2>&1; then
              git checkout -B state origin/state
            else
              git checkout -B state
            fi
            mkdir -p state
            cp "$RUNNER_TEMP/seen.json" state/seen.json
            git add -f state/seen.json
            if git diff --cached --quiet; then
              echo "bez zmian"
              exit 0
            fi
            git commit -m "state: $(date -u +%FT%TZ)"
            git push origin state && exit 0
          done
          exit 1
```

Trzy rzeczy, bez których to nie działa:

- **Ścieżka odczytu musi być identyczna ze ścieżką zapisu.** Commitujemy `state/seen.json`, więc
  `git show` musi pytać o `origin/state:state/seen.json`. Przy niezgodności stan nigdy się nie
  wczyta, każdy cykl jest zimnym startem i narzędzie **nigdy nie wyśle powiadomienia**.
- **Świeży stan jest odkładany do `$RUNNER_TEMP` przed pętlą i przywracany po każdym resecie.**
  To brakujący trzeci element wymagany przez specyfikację: „fetch + `reset --hard` + **ponowne
  zastosowanie zapisu**". Bez kopiowania `checkout -B state origin/state` nadpisałby właśnie
  wygenerowany plik starą wersją.
- **Gałąź jest bazowana na `origin/state`**, nie na HEAD-zie `main` — inaczej od drugiego
  uruchomienia każdy push leciałby jako non-fast-forward.

`git diff --cached --quiet` realizuje regułę „commit tylko przy realnej zmianie"; bez niego gałąź
dostawałaby 8640 pustych commitów miesięcznie. Pętla używa `reset`/`checkout`, nie `rebase`, bo
konflikt na pliku JSON nie scaliłby się automatycznie.

- [ ] **Step 2: Commit**

```bash
git add .github
git commit -m "ci: add scheduled check workflow"
```

---

## Task 17: Uruchomienie i weryfikacja end-to-end

- [ ] **Step 1: Uruchom pełny zestaw testów**

Run: `.venv/bin/pytest -v`
Expected: wszystko zielone. Nie idź dalej przy jakiejkolwiek porażce.

- [ ] **Step 2: Utwórz bota i ustal `chat_id`**

Użytkownik: `/newbot` u @BotFather, potem napisz cokolwiek do bota. Zmienne podajemy przez `export`
w powłoce — plan nie używa pliku `.env` i nie wciąga `python-dotenv`.

```bash
export TELEGRAM_BOT_TOKEN="..."
.venv/bin/python tools/get_chat_id.py
```

- [ ] **Step 2a: Uzupełnij `config.yaml` realnymi danymi**

Kroki 4 i 6 zakładają film **aktualnie grany** we wskazanym kinie — bez tego „niepusty
`seen_events`" i `--force-send` nie mają czego znaleźć, a placeholder z zadania 5 tego nie
gwarantuje.

```bash
.venv/bin/python tools/list_cinemas.py krak
```

Wpisz wybrany numer kina do `cinemas`, a w `watch` podaj fragment tytułu widocznego w
`tests/fixtures/film_events_1090.json` (pole `films[].name`). Dalsze kroki zakładają, że fraza z
`match` to `Backrooms` — jeśli wybierzesz inny tytuł, podstawiaj go konsekwentnie.

- [ ] **Step 3: Przebieg próbny**

```bash
TELEGRAM_BOT_TOKEN=x TELEGRAM_CHAT_ID=y .venv/bin/python -m ccdrop.main --dry-run --verbose
```

Oczekiwane: cykl przechodzi, wypisuje co by wysłał, `state/seen.json` **nie powstaje**.

- [ ] **Step 4: Zimny start**

```bash
.venv/bin/python -m ccdrop.main
```

Oczekiwane: brak wiadomości, `state/seen.json` powstaje z `warm: true` i niepustym `seen_events`.

- [ ] **Step 5: Drugi przebieg**

Uruchom ponownie. Oczekiwane: brak wiadomości, stan bez zmian.

- [ ] **Step 6: Realna wysyłka**

```bash
.venv/bin/python -m ccdrop.main --force-send Backrooms
```

Oczekiwane: wiadomość dociera na Telegram, ma poprawne polskie dni tygodnia, działające linki
i prawidłową odmianę liczebnika.

- [ ] **Step 7: Symulacja awarii wysyłki**

Usuń ze stanu jedno ID z `seen_events` **oraz** odpowiadający mu klucz z `http_cache`. Samo usunięcie
ID nie wystarczy — wpis w cache spowodowałby `304`, więc cykl nie pobrałby żadnego eventu i nie
byłoby czego wysyłać.

```bash
python - <<'PY'
import json, pathlib
p = pathlib.Path("state/seen.json")
s = json.loads(p.read_text())
key = next(iter(s["watch_state"]))
event_id, day = next(iter(s["watch_state"][key]["seen_events"].items()))
del s["watch_state"][key]["seen_events"][event_id]
s["http_cache"].pop(f"{key.rsplit('|', 1)[1]}|{day}", None)
p.write_text(json.dumps(s, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
print("usunieto", event_id, day)
PY

TELEGRAM_BOT_TOKEN=zly TELEGRAM_CHAT_ID=y .venv/bin/python -m ccdrop.main
```

Oczekiwane: wysyłka zawodzi, `http_cache` **nie drgnął**, a `seen_events` nie zyskał usuniętego ID.
Kolejny przebieg z poprawnym tokenem dostarcza ten sam drop.

- [ ] **Step 8: Utwórz publiczne repo i wypchnij**

**Krok wymagający zgody użytkownika — zapytaj przed wykonaniem.**

```bash
git remote add origin git@github-personal:Laaidback/cinema-city-drop-detector.git
git push -u origin main
```

Repo trzeba wcześniej założyć na `https://github.com/new` jako **publiczne**.

- [ ] **Step 9: Dodaj sekrety i uruchom workflow ręcznie**

Sekrety w `Settings → Secrets and variables → Actions`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
Potem `Actions → check → Run workflow`.

Oczekiwane: job zielony, gałąź `state` powstaje z plikiem `seen.json`.

- [ ] **Step 10: Drugie uruchomienie ręczne**

Oczekiwane: job zielony, log zawiera `bez zmian`, **brak nowego commita** na gałęzi `state`.

- [ ] **Step 11: Dodaj drugi wpis `watch` po dobie działania**

Dopisz do `config.yaml` film już grany w tym samym kinie. Oczekiwane: cykl milczy (zimny start przy
pełnym `http_cache`), a kolejna zmiana repertuaru nie wywołuje lawiny starych seansów. To jedyna
pułapka, której pierwsze uruchomienie nie ujawnia.
