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
