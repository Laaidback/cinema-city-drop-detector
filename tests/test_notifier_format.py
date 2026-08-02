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


def test_singular_form():
    assert plural_screenings(1) == "1 nowy seans"


def test_few_form():
    assert plural_screenings(3) == "3 nowe seanse"


def test_many_form():
    assert plural_screenings(6) == "6 nowych seansów"


def test_teens_take_genitive():
    assert plural_screenings(13) == "13 nowych seansów"


def test_header_uses_cinema_name():
    text = format_drop(drop_with([event("1")]), {"1090": "Kraków Bonarka"})

    assert "Kraków Bonarka" in text


def test_header_falls_back_to_cinema_id():
    text = format_drop(drop_with([event("1")]), {})

    assert "1090" in text


def test_known_attribute_is_labelled():
    text = format_drop(drop_with([event("1", attrs=("dolby-cinema",))]), {})

    assert "Dolby Cinema" in text


def test_unknown_attribute_is_dropped():
    text = format_drop(drop_with([event("1", attrs=("subbed",))]), {})

    assert "subbed" not in text


def test_weekday_is_polish_abbreviation():
    text = format_drop(drop_with([event("1", day="2026-08-15")]), {})

    assert "sb 15.08" in text


def test_list_is_truncated_after_fifteen():
    events = [event(str(i), time=f"{i % 24:02d}:00") for i in range(20)]
    text = format_drop(drop_with(events), {})

    assert "…i 5 więcej" in text
