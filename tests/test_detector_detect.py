from ccdrop.detector import detect
from ccdrop.models import Config, Event, WatchEntry, WatchState


def event(eid, name="Backrooms. Bez wyjścia", cinema="1090", day="2026-08-15"):
    return Event(
        id=eid,
        film_id="f1",
        film_name=name,
        cinema_id=cinema,
        business_day=day,
        date_time=f"{day}T18:30:00",
        auditorium="Sala 4",
        booking_link=f"https://tickets.cinema-city.pl/api/order/{eid}",
        attribute_ids=("imax",),
    )


CONFIG = Config(horizon_days=90, cinemas=("1090",), watch=(WatchEntry(match="Backrooms"),))


def test_cold_start_sends_nothing():
    result = detect(CONFIG, {}, [event("1")], {"1090"})

    assert result.drops == ()


def test_cold_start_records_baseline():
    result = detect(CONFIG, {}, [event("1")], {"1090"})

    assert result.baselines == {"Backrooms|1090": {"1": "2026-08-15"}}


def test_cinema_without_dates_list_stays_cold():
    result = detect(CONFIG, {}, [event("1")], set())

    assert result.baselines == {}


def test_warm_pair_reports_new_event():
    state = {"Backrooms|1090": WatchState(warm=True, seen_events={})}
    result = detect(CONFIG, state, [event("1")], set())

    assert result.drops[0].events[0].id == "1"


def test_known_event_is_not_reported():
    state = {"Backrooms|1090": WatchState(warm=True, seen_events={"1": "2026-08-15"})}
    result = detect(CONFIG, state, [event("1")], set())

    assert result.drops == ()


def test_unmatched_film_is_ignored():
    state = {"Backrooms|1090": WatchState(warm=True, seen_events={})}
    result = detect(CONFIG, state, [event("1", name="Diuna 3")], set())

    assert result.drops == ()


def test_events_are_grouped_per_film():
    state = {"Backrooms|1090": WatchState(warm=True, seen_events={})}
    events = [event("1"), event("2", name="Backrooms. Wersja rozszerzona")]
    result = detect(CONFIG, state, events, set())

    assert len(result.drops) == 2


def test_force_match_reports_already_seen_event():
    state = {"Backrooms|1090": WatchState(warm=True, seen_events={"1": "2026-08-15"})}
    result = detect(CONFIG, state, [event("1")], set(), force_match="Backrooms")

    assert result.drops[0].events[0].id == "1"


def test_adding_cinema_cold_starts_only_new_pair():
    config = Config(
        horizon_days=90, cinemas=("1090", "1064"), watch=(WatchEntry(match="Backrooms"),)
    )
    state = {"Backrooms|1090": WatchState(warm=True, seen_events={})}
    events = [event("1"), event("2", cinema="1064")]
    result = detect(config, state, events, {"1090", "1064"})

    assert set(result.baselines) == {"Backrooms|1064"}
