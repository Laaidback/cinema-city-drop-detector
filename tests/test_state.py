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
