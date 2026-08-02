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
