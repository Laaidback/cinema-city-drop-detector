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
