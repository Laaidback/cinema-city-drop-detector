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
        attrs = item.get("attributes")
        attribute_ids = tuple(str(a) for a in attrs) if attrs else None
        entries.append(WatchEntry(match=match, cinemas=own_ids, attributes=attribute_ids))

    return Config(
        horizon_days=int(raw.get("horizon_days", 90)),
        cinemas=cinemas,
        watch=tuple(entries),
    )
