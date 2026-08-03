import json
from datetime import date, timedelta
from pathlib import Path

from ccdrop.models import State, WatchState

FILENAME = "seen.json"
VERSION = 1
DROP_LOG_RETENTION_DAYS = 60


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
        cinema_names=dict(raw.get("cinema_names", {})),
        drop_log=list(raw.get("drop_log", [])),
    )


def serialize(state: State) -> str:
    payload = {
        "version": VERSION,
        "watch_state": {
            key: {"warm": v.warm, "seen_events": v.seen_events}
            for key, v in state.watch_state.items()
        },
        "cinema_names": state.cinema_names,
        "drop_log": state.drop_log,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def prune(state: State, today: str) -> State:
    watch = {
        key: WatchState(
            warm=v.warm,
            seen_events={eid: day for eid, day in v.seen_events.items() if day >= today},
        )
        for key, v in state.watch_state.items()
    }
    oldest = (date.fromisoformat(today) - timedelta(days=DROP_LOG_RETENTION_DAYS)).isoformat()
    drop_log = [entry for entry in state.drop_log if entry["detected_at"][:10] >= oldest]
    return State(watch_state=watch, cinema_names=dict(state.cinema_names), drop_log=drop_log)


def save_state(state_dir: Path, state: State, today: str) -> None:
    directory = Path(state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / FILENAME
    tmp = directory / f"{FILENAME}.tmp"
    tmp.write_text(serialize(prune(state, today)), encoding="utf-8")
    tmp.replace(target)

