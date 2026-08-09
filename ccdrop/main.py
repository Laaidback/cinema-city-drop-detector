import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from ccdrop.chains import chain_of
from ccdrop.config import load_config
from ccdrop.detector import detect
from ccdrop.models import Config, Drop, State, WatchState
from ccdrop.notifier import TelegramNotifier, format_drop
from ccdrop.providers import build_providers
from ccdrop.schedule import WARSAW, in_window
from ccdrop.state import load_state, save_state

log = logging.getLogger("ccdrop")
PART_INTERVAL_SECONDS = 1.2


def current_time() -> datetime:
    return datetime.now(WARSAW)


def drop_log_entry(drop: Drop, now: datetime) -> dict:
    return {
        "detected_at": now.astimezone(WARSAW).isoformat(timespec="seconds"),
        "film": drop.film_name,
        "cinema": drop.cinema_id,
        "count": len(drop.events),
        "notified": drop.notify,
    }


def preview(drops, cinema_names) -> None:
    for drop in drops:
        if not drop.notify:
            continue
        for part in format_drop(drop, cinema_names):
            print(part)
            print()


def send_parts(notifier, parts: list[str], sleep=time.sleep) -> bool:
    for index, part in enumerate(parts):
        if index:
            sleep(PART_INTERVAL_SECONDS)
        if not notifier.send(part):
            return False
    return True


def run_cycle(config, state, providers, notifier, today, now, dry_run=False, force_match=None):
    names = {}
    for chain in sorted({chain_of(cinema_id) for cinema_id in config.cinemas}):
        names.update(providers[chain].cinema_names(today, config.horizon_days))
    cinema_names = {**state.cinema_names, **names}

    fetched_events = []
    complete = set()

    for cinema_id in config.cinemas:
        events = providers[chain_of(cinema_id)].fetch(cinema_id, today, config.horizon_days)
        if events is None:
            continue
        complete.add(cinema_id)
        fetched_events.extend(events)

    outcome = detect(config, state.watch_state, fetched_events, complete, force_match)
    log.info("Pobrano %d seansów, wykryto %d grup", len(fetched_events), len(outcome.drops))

    if dry_run:
        preview(outcome.drops, cinema_names)
        return state

    delivered: dict[str, dict[str, str]] = {}
    logged: list[dict] = []
    for drop in outcome.drops:
        if drop.notify and not send_parts(notifier, format_drop(drop, cinema_names)):
            continue
        delivered.setdefault(drop.watch_key, {}).update(
            {e.id: e.business_day for e in drop.events}
        )
        logged.append(drop_log_entry(drop, now))

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
    now = current_time()
    if config.schedule and not in_window(config.schedule, now):
        log.info("%s poza oknem harmonogramu, cykl pominięty", now.strftime("%H:%M"))
        return 0

    if args.force_send and not any(e.match == args.force_send for e in config.watch):
        log.warning("--force-send %s nie pasuje do żadnego wpisu watch", args.force_send)

    state = load_state(args.state_dir)
    today = now.date().isoformat()

    updated = run_cycle(
        config,
        state,
        build_providers(),
        build_notifier(args.dry_run),
        today,
        now,
        dry_run=args.dry_run,
        force_match=args.force_send,
    )

    if not args.dry_run:
        save_state(args.state_dir, updated, today)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
