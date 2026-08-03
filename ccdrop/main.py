import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ccdrop import api as api_module
from ccdrop.api import ApiClient, CinemaCityApi
from ccdrop.config import load_config
from ccdrop.detector import detect
from ccdrop.models import Config, Drop, State, WatchState
from ccdrop.notifier import TelegramNotifier, format_drop
from ccdrop.state import load_state, prune, save_state

log = logging.getLogger("ccdrop")
WARSAW = ZoneInfo("Europe/Warsaw")


def horizon_date(today: str, days: int) -> str:
    return (date.fromisoformat(today) + timedelta(days=days)).isoformat()


def drop_log_entry(drop: Drop, now: datetime) -> dict:
    return {
        "detected_at": now.astimezone(WARSAW).isoformat(timespec="seconds"),
        "film": drop.film_name,
        "cinema": drop.cinema_id,
        "count": len(drop.events),
    }


def run_cycle(config, state, api, notifier, today, now, dry_run=False, force_match=None):
    until = horizon_date(today, config.horizon_days)
    names = api.fetch_cinema_names(until)
    cinema_names = {**state.cinema_names, **names}

    fetched_events = []
    complete = set()

    for cinema_id in config.cinemas:
        dates = api.fetch_dates(cinema_id, until)
        if dates is None:
            continue
        complete.add(cinema_id)
        for day in dates:
            result = api.fetch_events(cinema_id, day)
            if result.status is api_module.FetchOutcome.FAILED:
                continue
            fetched_events.extend(api_module.parse_film_events(result.payload))

    outcome = detect(config, state.watch_state, fetched_events, complete, force_match)
    log.info("Pobrano %d seansów, wykryto %d grup", len(fetched_events), len(outcome.drops))

    delivered: dict[str, dict[str, str]] = {}
    logged: list[dict] = []
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
            logged.append(drop_log_entry(drop, now))

    if dry_run:
        return state

    new_watch = dict(state.watch_state)
    for key, events in delivered.items():
        current = new_watch.get(key, WatchState())
        merged = {**current.seen_events, **events}
        new_watch[key] = WatchState(warm=True, seen_events=merged)
    for key, baseline in outcome.baselines.items():
        new_watch[key] = WatchState(warm=True, seen_events=dict(baseline))

    return State(
        watch_state=new_watch,
        cinema_names=cinema_names,
        drop_log=[*state.drop_log, *logged],
    )


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
    now = datetime.now(WARSAW)
    today = now.date().isoformat()

    updated = run_cycle(
        config,
        state,
        CinemaCityApi(ApiClient()),
        build_notifier(args.dry_run),
        today,
        now,
        dry_run=args.dry_run,
        force_match=args.force_send,
    )

    if not args.dry_run:
        save_state(args.state_dir, prune(updated, today))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
