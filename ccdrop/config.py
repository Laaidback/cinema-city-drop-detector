from pathlib import Path

import yaml

from ccdrop.chains import CHAIN_SEPARATOR, chain_of, prefixed
from ccdrop.models import Config, Schedule, WatchEntry
from ccdrop.providers import DEFAULT_CHAIN, PROVIDERS

MAX_MARGIN_SUM = 59


def normalise_cinema_id(value) -> str:
    text = str(value)
    cinema_id = text if CHAIN_SEPARATOR in text else prefixed(DEFAULT_CHAIN, text)
    if chain_of(cinema_id) not in PROVIDERS:
        raise ValueError(f"cinemas: nieznana sieć kin w wartości '{text}'")
    return cinema_id


def parse_schedule(raw) -> Schedule | None:
    if not raw:
        return None

    hours = raw.get("hours")
    if not isinstance(hours, list) or len(hours) != 2:
        raise ValueError("schedule/hours: wymagane dokładnie dwie godziny [start, koniec]")
    if not all(isinstance(hour, int) and 0 <= hour <= 23 for hour in hours):
        raise ValueError("schedule/hours: godziny muszą być liczbami z zakresu 0-23")
    start, end = hours
    if start > end:
        raise ValueError("schedule/hours: start nie może być późniejszy niż koniec")

    before = raw.get("before", 0)
    after = raw.get("after", 0)
    if not isinstance(before, int) or before < 0:
        raise ValueError("schedule/before: wymagana liczba całkowita nieujemna")
    if not isinstance(after, int) or after < 0:
        raise ValueError("schedule/after: wymagana liczba całkowita nieujemna")
    if before + after >= MAX_MARGIN_SUM:
        raise ValueError(
            "schedule: before + after musi być mniejsze niż 59, inaczej okna nachodzą na siebie"
        )

    return Schedule(hours=(start, end), before=before, after=after)


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}

    cinemas = tuple(normalise_cinema_id(c) for c in raw.get("cinemas", []))
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
        own_ids = tuple(normalise_cinema_id(c) for c in own) if own else None
        for cinema in own_ids or ():
            if cinema not in cinemas:
                raise ValueError(f"watch/{match}: kino {cinema} spoza globalnej listy cinemas")
        attrs = item.get("attributes")
        attribute_ids = tuple(str(a) for a in attrs) if attrs else None
        notify = item.get("notify", True)
        if not isinstance(notify, bool):
            raise ValueError(f"watch/{match}: notify wymaga wartości true albo false")
        entries.append(
            WatchEntry(match=match, cinemas=own_ids, attributes=attribute_ids, notify=notify)
        )

    return Config(
        horizon_days=int(raw.get("horizon_days", 90)),
        cinemas=cinemas,
        watch=tuple(entries),
        schedule=parse_schedule(raw.get("schedule")),
    )
