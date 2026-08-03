from ccdrop.detector import detect, watch_key
from ccdrop.models import Config, Event, WatchEntry, WatchState


def event(eid, name="Backrooms. Bez wyjścia", cinema="1090", day="2026-08-15", attrs=("imax",)):
    return Event(
        id=eid,
        film_id="f1",
        film_name=name,
        cinema_id=cinema,
        business_day=day,
        date_time=f"{day}T18:30:00",
        auditorium="Sala 4",
        booking_link=f"https://tickets.cinema-city.pl/api/order/{eid}",
        attribute_ids=attrs,
    )


CONFIG = Config(horizon_days=90, cinemas=("1090",), watch=(WatchEntry(match="Backrooms"),))
IMAX_CONFIG = Config(
    horizon_days=90,
    cinemas=("1090",),
    watch=(WatchEntry(match="Backrooms", attributes=("imax",)),),
)


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


def test_entry_without_attributes_reports_any_format():
    state = {"Backrooms|1090": WatchState(warm=True, seen_events={})}
    result = detect(CONFIG, state, [event("1", attrs=("2d", "subbed"))], set())

    assert result.drops[0].events[0].id == "1"


def test_required_attribute_reports_event_carrying_it():
    state = {"Backrooms|1090|imax": WatchState(warm=True, seen_events={})}
    result = detect(IMAX_CONFIG, state, [event("1", attrs=("imax", "subbed"))], set())

    assert result.drops[0].events[0].id == "1"


def test_required_attribute_ignores_event_without_it():
    state = {"Backrooms|1090|imax": WatchState(warm=True, seen_events={})}
    result = detect(IMAX_CONFIG, state, [event("1", attrs=("2d",))], set())

    assert result.drops == ()


def test_event_with_one_of_two_required_attributes_is_ignored():
    config = Config(
        horizon_days=90,
        cinemas=("1090",),
        watch=(WatchEntry(match="Backrooms", attributes=("imax", "vip")),),
    )
    state = {"Backrooms|1090|imax,vip": WatchState(warm=True, seen_events={})}
    result = detect(config, state, [event("1", attrs=("imax",))], set())

    assert result.drops == ()


def test_filtered_event_stays_out_of_baseline():
    result = detect(IMAX_CONFIG, {}, [event("1", attrs=("2d",))], {"1090"})

    assert result.baselines == {"Backrooms|1090|imax": {}}


def test_attributes_change_watch_key():
    plain = watch_key(WatchEntry(match="Backrooms"), "1090")
    filtered = watch_key(WatchEntry(match="Backrooms", attributes=("imax",)), "1090")

    assert filtered != plain


def test_attribute_order_does_not_change_watch_key():
    ascending = watch_key(WatchEntry(match="Backrooms", attributes=("imax", "vip")), "1090")
    descending = watch_key(WatchEntry(match="Backrooms", attributes=("vip", "imax")), "1090")

    assert ascending == descending
