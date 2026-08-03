from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from ccdrop.main import run_cycle
from ccdrop.models import Config, WatchEntry

CONFIG = Config(horizon_days=90, cinemas=("1090",), watch=(WatchEntry(match="Backrooms"),))
NOW = datetime(2026, 8, 3, 9, 1, 12, tzinfo=ZoneInfo("Europe/Warsaw"))


def test_failed_send_does_not_record_seen_events(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=False)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert state.watch_state["Backrooms|1090"].seen_events == {}


def test_successful_send_records_seen_events(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert state.watch_state["Backrooms|1090"].seen_events == {"1": "2026-08-15"}


def test_cold_pair_warms_without_sending(fake_world):
    world = fake_world(warm=False, events=[("1", "2026-08-15")], send_ok=True)
    run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert world.notifier.sent == []


def test_cold_pair_records_baseline(fake_world):
    world = fake_world(warm=False, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert state.watch_state["Backrooms|1090"].seen_events == {"1": "2026-08-15"}


def test_dates_failure_leaves_pairs_cold(fake_world):
    world = fake_world(warm=False, events=[], dates_fail=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert state.watch_state.get("Backrooms|1090") is None


def test_dry_run_records_no_seen_events(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(
        CONFIG, world.state, world.api, world.notifier, "2026-08-02", NOW, dry_run=True
    )

    assert state.watch_state["Backrooms|1090"].seen_events == {}


def test_dry_run_does_not_warm_cold_pair(fake_world):
    world = fake_world(warm=False, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(
        CONFIG, world.state, world.api, world.notifier, "2026-08-02", NOW, dry_run=True
    )

    assert state.watch_state == {}


def test_dry_run_sends_nothing(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    run_cycle(CONFIG, world.state, world.api, world.notifier, "2026-08-02", NOW, dry_run=True)

    assert world.notifier.sent == []


def test_dry_run_needs_no_notifier(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, None, "2026-08-02", NOW, dry_run=True)

    assert state is world.state


def test_existing_seen_events_survive_new_drop(fake_world):
    world = fake_world(warm=True, events=[("2", "2026-08-16")], send_ok=True)
    world.state.watch_state["Backrooms|1090"].seen_events["1"] = "2026-08-15"
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert "1" in state.watch_state["Backrooms|1090"].seen_events


def test_repeat_after_failed_send_delivers_again(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=False)
    after_failure = run_cycle(
        CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW
    )
    world.notifier.ok = True
    run_cycle(CONFIG, after_failure, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert len(world.notifier.sent) == 2


def test_pair_warms_despite_failing_date(fake_world):
    world = fake_world(warm=False, events=[("1", "2026-08-15")], failed_dates=["2026-08-16"])
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert state.watch_state["Backrooms|1090"].warm is True


def test_failing_date_stays_out_of_baseline(fake_world):
    world = fake_world(
        warm=False, events=[("1", "2026-08-15"), ("2", "2026-08-16")], failed_dates=["2026-08-16"]
    )
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert "2" not in state.watch_state["Backrooms|1090"].seen_events


def test_force_send_keeps_existing_seen_events(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    world.state.watch_state["Backrooms|1090"].seen_events["9"] = "2026-08-20"
    state = run_cycle(
        CONFIG, world.state, world.api, world.notifier, "2026-08-02", NOW, force_match="Backrooms"
    )

    assert "9" in state.watch_state["Backrooms|1090"].seen_events


def test_force_send_reports_event_already_in_seen_events(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    world.state.watch_state["Backrooms|1090"].seen_events["1"] = "2026-08-15"
    run_cycle(
        CONFIG, world.state, world.api, world.notifier, "2026-08-02", NOW, force_match="Backrooms"
    )

    assert world.notifier.sent != []


def test_cinema_names_merge_into_state(fake_world):
    world = fake_world(warm=True, events=[])
    world.state.cinema_names["1064"] = "Zakopianka"
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert state.cinema_names["1064"] == "Zakopianka"


def test_delivered_group_appends_one_drop_log_entry(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15"), ("2", "2026-08-16")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert len(state.drop_log) == 1


def test_drop_log_entry_records_detection_time(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert state.drop_log[0]["detected_at"] == "2026-08-03T09:01:12+02:00"


def test_drop_log_entry_records_whole_seconds(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(
        CONFIG,
        world.state,
        world.api,
        world.notifier,
        today="2026-08-02",
        now=NOW.replace(microsecond=987654),
    )

    assert state.drop_log[0]["detected_at"] == "2026-08-03T09:01:12+02:00"


def test_drop_log_entry_records_warsaw_offset_for_utc_now(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(
        CONFIG,
        world.state,
        world.api,
        world.notifier,
        today="2026-08-02",
        now=datetime(2026, 8, 3, 7, 1, 12, tzinfo=UTC),
    )

    assert state.drop_log[0]["detected_at"] == "2026-08-03T09:01:12+02:00"


def test_drop_log_entry_records_film(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert state.drop_log[0]["film"] == "Backrooms. Bez wyjścia"


def test_drop_log_entry_records_cinema(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert state.drop_log[0]["cinema"] == "1090"


def test_drop_log_entry_records_count(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15"), ("2", "2026-08-16")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert state.drop_log[0]["count"] == 2


def test_failed_send_appends_no_drop_log_entry(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=False)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert state.drop_log == []


def test_dry_run_appends_no_drop_log_entry(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(
        CONFIG, world.state, world.api, world.notifier, "2026-08-02", NOW, dry_run=True
    )

    assert state.drop_log == []


def test_cold_pair_appends_no_drop_log_entry(fake_world):
    world = fake_world(warm=False, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert state.drop_log == []


def test_existing_drop_log_entries_survive_new_drop(fake_world):
    world = fake_world(warm=True, events=[("2", "2026-08-16")], send_ok=True)
    world.state.drop_log.append(
        {
            "detected_at": "2026-08-01T10:00:00+02:00",
            "film": "Odyseja",
            "cinema": "1060",
            "count": 3,
        }
    )
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02", now=NOW)

    assert state.drop_log[0]["film"] == "Odyseja"
