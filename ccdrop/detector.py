from collections import defaultdict
from dataclasses import dataclass

from ccdrop.matching import matches
from ccdrop.models import Config, Drop, Event, WatchEntry, WatchState


@dataclass(frozen=True)
class DetectResult:
    drops: tuple[Drop, ...]
    baselines: dict[str, dict[str, str]]


def watch_key(entry: WatchEntry, cinema_id: str) -> str:
    if not entry.attributes:
        return f"{entry.match}|{cinema_id}"
    return f"{entry.match}|{cinema_id}|{','.join(sorted(entry.attributes))}"


def has_required_attributes(entry: WatchEntry, event: Event) -> bool:
    return all(attribute in event.attribute_ids for attribute in entry.attributes or ())


def entry_cinemas(config: Config, entry: WatchEntry) -> tuple[str, ...]:
    return entry.cinemas or config.cinemas


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
                if e.cinema_id == cinema_id
                and matches(entry.match, e.film_name)
                and has_required_attributes(entry, e)
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
                        notify=entry.notify,
                    )
                )

    return DetectResult(drops=tuple(drops), baselines=baselines)
