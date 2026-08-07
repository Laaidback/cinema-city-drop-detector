import re

from ccdrop.models import Drop, Event
from ccdrop.notifier import format_drop, plural_screenings


def event(eid, day="2026-08-15", time="18:30", attrs=("imax",)):
    return Event(
        id=eid,
        film_id="f1",
        film_name="Backrooms. Bez wyjścia",
        cinema_id="1090",
        business_day=day,
        date_time=f"{day}T{time}:00",
        auditorium="Sala 4",
        booking_link=f"https://tickets.cinema-city.pl/api/order/{eid}",
        attribute_ids=attrs,
    )


def drop_with(events):
    return Drop(
        watch_key="Backrooms|1090",
        film_name="Backrooms. Bez wyjścia",
        cinema_id="1090",
        events=tuple(events),
    )


def many_events(count):
    return [event(str(i), time=f"{i % 24:02d}:00") for i in range(count)]


def test_singular_form():
    assert plural_screenings(1) == "1 nowy seans"


def test_few_form():
    assert plural_screenings(3) == "3 nowe seanse"


def test_many_form():
    assert plural_screenings(6) == "6 nowych seansów"


def test_teens_take_genitive():
    assert plural_screenings(13) == "13 nowych seansów"


def test_header_uses_cinema_name():
    parts = format_drop(drop_with([event("1")]), {"1090": "Kraków Bonarka"})

    assert "Kraków Bonarka" in parts[0]


def test_header_falls_back_to_cinema_id():
    parts = format_drop(drop_with([event("1")]), {})

    assert "1090" in parts[0]


def test_known_attribute_is_labelled():
    parts = format_drop(drop_with([event("1", attrs=("dolby-cinema",))]), {})

    assert "Dolby Cinema" in parts[0]


def test_unknown_attribute_is_dropped():
    parts = format_drop(drop_with([event("1", attrs=("subbed",))]), {})

    assert "subbed" not in parts[0]


def test_weekday_is_polish_abbreviation():
    parts = format_drop(drop_with([event("1", day="2026-08-15")]), {})

    assert "sb 15.08" in parts[0]


def test_short_drop_produces_one_part():
    parts = format_drop(drop_with(many_events(3)), {})

    assert len(parts) == 1


def test_single_part_carries_no_counter():
    parts = format_drop(drop_with(many_events(3)), {})

    assert "(1/1)" not in parts[0]


def test_long_drop_produces_several_parts():
    parts = format_drop(drop_with(many_events(120)), {})

    assert len(parts) > 1


def test_parts_carry_every_screening_exactly_once():
    parts = format_drop(drop_with(many_events(120)), {})

    assert re.findall(r"order/(\d+)", "\n".join(parts)) == [str(i) for i in range(120)]


def test_no_part_exceeds_budget():
    parts = format_drop(drop_with(many_events(120)), {})

    assert max(len(part) for part in parts) <= 3500


def test_every_part_repeats_film_name():
    parts = format_drop(drop_with(many_events(120)), {})

    assert all("Backrooms. Bez wyjścia" in part for part in parts)


def test_later_part_is_numbered():
    parts = format_drop(drop_with(many_events(120)), {})

    assert f"(2/{len(parts)})" in parts[1]


def test_later_part_header_counts_whole_drop():
    parts = format_drop(drop_with(many_events(120)), {})

    assert "120 nowych seansów" in parts[1]


def test_no_part_announces_hidden_screenings():
    parts = format_drop(drop_with(many_events(120)), {})

    assert "więcej" not in "\n".join(parts)
