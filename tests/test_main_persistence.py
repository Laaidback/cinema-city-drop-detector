from ccdrop.main import run_cycle
from ccdrop.models import Config, State, WatchEntry, WatchState

CONFIG = Config(horizon_days=90, cinemas=("1090",), watch=(WatchEntry(match="Backrooms"),))


def test_failed_send_does_not_record_seen_events(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=False)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert state.watch_state["Backrooms|1090"].seen_events == {}


def test_successful_send_records_seen_events(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert state.watch_state["Backrooms|1090"].seen_events == {"1": "2026-08-15"}


def test_failed_send_blocks_all_http_cache_updates(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=False)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert state.http_cache == {}


def test_failed_fetch_removes_cache_entry(fake_world):
    world = fake_world(warm=True, events=[], failed_dates=["2026-08-15"])
    world.state.http_cache["1090|2026-08-15"] = "stary"
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert "1090|2026-08-15" not in state.http_cache


def test_cold_pair_warms_without_sending(fake_world):
    world = fake_world(warm=False, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert world.notifier.sent == []


def test_cold_pair_forces_unconditional_fetch(fake_world):
    world = fake_world(warm=False, events=[("1", "2026-08-15")])
    world.state.http_cache["1090|2026-08-15"] = "stary"
    run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert world.api.conditional_calls == []


def test_dates_failure_leaves_pairs_cold(fake_world):
    world = fake_world(warm=False, events=[], dates_fail=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert state.watch_state.get("Backrooms|1090") is None


def test_dry_run_records_no_seen_events(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, "2026-08-02", dry_run=True)

    assert state.watch_state["Backrooms|1090"].seen_events == {}


def test_dry_run_records_no_http_cache(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, "2026-08-02", dry_run=True)

    assert state.http_cache == {}


def test_dry_run_does_not_warm_cold_pair(fake_world):
    world = fake_world(warm=False, events=[("1", "2026-08-15")], send_ok=True)
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, "2026-08-02", dry_run=True)

    assert state.watch_state == {}


def test_dry_run_sends_nothing(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    run_cycle(CONFIG, world.state, world.api, world.notifier, "2026-08-02", dry_run=True)

    assert world.notifier.sent == []


def test_existing_seen_events_survive_new_drop(fake_world):
    world = fake_world(warm=True, events=[("2", "2026-08-16")], send_ok=True)
    world.state.watch_state["Backrooms|1090"].seen_events["1"] = "2026-08-15"
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert "1" in state.watch_state["Backrooms|1090"].seen_events


def test_repeat_after_failed_send_delivers_again(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=False)
    after_failure = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")
    world.notifier.ok = True
    run_cycle(CONFIG, after_failure, world.api, world.notifier, today="2026-08-02")

    assert len(world.notifier.sent) == 2


def test_pair_warms_despite_failing_date(fake_world):
    world = fake_world(warm=False, events=[("1", "2026-08-15")], failed_dates=["2026-08-16"])
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert state.watch_state["Backrooms|1090"].warm is True


def test_failing_date_leaves_no_cache_entry(fake_world):
    world = fake_world(warm=False, events=[("1", "2026-08-15")], failed_dates=["2026-08-16"])
    world.state.http_cache["1090|2026-08-16"] = "stary"
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert "1090|2026-08-16" not in state.http_cache


def test_force_send_bypasses_conditional_fetch(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    world.state.http_cache["1090|2026-08-15"] = "stary"
    run_cycle(CONFIG, world.state, world.api, world.notifier, "2026-08-02", force_match="Backrooms")

    assert world.api.conditional_calls == []


def test_force_send_keeps_existing_seen_events(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    world.state.watch_state["Backrooms|1090"].seen_events["9"] = "2026-08-20"
    state = run_cycle(
        CONFIG, world.state, world.api, world.notifier, "2026-08-02", force_match="Backrooms"
    )

    assert "9" in state.watch_state["Backrooms|1090"].seen_events


def test_failed_fetch_deletes_cache_even_when_send_fails(fake_world):
    world = fake_world(
        warm=True, events=[("1", "2026-08-15")], send_ok=False, failed_dates=["2026-08-16"]
    )
    world.state.http_cache["1090|2026-08-16"] = "stary"
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert "1090|2026-08-16" not in state.http_cache


def test_force_send_reports_event_already_in_seen_events(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    world.state.watch_state["Backrooms|1090"].seen_events["1"] = "2026-08-15"
    run_cycle(CONFIG, world.state, world.api, world.notifier, "2026-08-02", force_match="Backrooms")

    assert world.notifier.sent != []


def test_unrelated_cache_entries_survive(fake_world):
    world = fake_world(warm=True, events=[("1", "2026-08-15")], send_ok=True)
    world.state.http_cache["1064|2026-09-01"] = "obcy"
    state = run_cycle(CONFIG, world.state, world.api, world.notifier, today="2026-08-02")

    assert state.http_cache["1064|2026-09-01"] == "obcy"
