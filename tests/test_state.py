from ccdrop.models import State, WatchState
from ccdrop.state import load_state, prune, save_state


def test_roundtrip_preserves_seen_events(tmp_path):
    state = State(watch_state={"A|1": WatchState(warm=True, seen_events={"1": "2026-08-15"})})
    save_state(tmp_path, state)

    assert load_state(tmp_path).watch_state["A|1"].seen_events == {"1": "2026-08-15"}


def test_missing_file_gives_empty_state(tmp_path):
    assert load_state(tmp_path).watch_state == {}


def test_corrupted_file_gives_empty_state(tmp_path):
    (tmp_path / "seen.json").write_text("{ to nie jest json")

    assert load_state(tmp_path).watch_state == {}


def test_serialization_is_deterministic(tmp_path):
    first = State(cinema_names={"1090": "Bonarka", "1064": "Zakopianka"})
    second = State(cinema_names={"1064": "Zakopianka", "1090": "Bonarka"})
    save_state(tmp_path, first)
    first_bytes = (tmp_path / "seen.json").read_bytes()
    save_state(tmp_path, second)

    assert (tmp_path / "seen.json").read_bytes() == first_bytes


def test_prune_drops_past_events():
    state = State(
        watch_state={
            "A|1": WatchState(warm=True, seen_events={"old": "2026-07-01", "new": "2026-09-01"})
        }
    )

    assert prune(state, today="2026-08-02").watch_state["A|1"].seen_events == {"new": "2026-09-01"}


def test_roundtrip_preserves_drop_log(tmp_path):
    entry = {
        "detected_at": "2026-08-03T09:01:12+02:00",
        "film": "Odyseja",
        "cinema": "1060",
        "count": 3,
    }
    save_state(tmp_path, State(drop_log=[entry]))

    assert load_state(tmp_path).drop_log == [
        {
            "detected_at": "2026-08-03T09:01:12+02:00",
            "film": "Odyseja",
            "cinema": "1060",
            "count": 3,
        }
    ]


def test_file_without_drop_log_loads_empty_drop_log(tmp_path):
    (tmp_path / "seen.json").write_text(
        '{"version": 1, "watch_state": {}, "cinema_names": {"1090": "Bonarka"}}'
    )

    assert load_state(tmp_path).drop_log == []


def test_prune_drops_entry_older_than_60_days():
    entry = {
        "detected_at": "2026-06-03T09:01:12+02:00",
        "film": "Odyseja",
        "cinema": "1060",
        "count": 3,
    }

    assert prune(State(drop_log=[entry]), today="2026-08-03").drop_log == []


def test_prune_keeps_recent_entry():
    entry = {
        "detected_at": "2026-08-01T09:01:12+02:00",
        "film": "Odyseja",
        "cinema": "1060",
        "count": 3,
    }

    assert prune(State(drop_log=[entry]), today="2026-08-03").drop_log == [
        {
            "detected_at": "2026-08-01T09:01:12+02:00",
            "film": "Odyseja",
            "cinema": "1060",
            "count": 3,
        }
    ]


def test_prune_keeps_entry_exactly_60_days_old():
    entry = {
        "detected_at": "2026-06-04T09:01:12+02:00",
        "film": "Odyseja",
        "cinema": "1060",
        "count": 3,
    }

    assert len(prune(State(drop_log=[entry]), today="2026-08-03").drop_log) == 1
