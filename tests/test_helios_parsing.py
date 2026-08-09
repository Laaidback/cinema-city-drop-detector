import json
from datetime import datetime
from pathlib import Path

from ccdrop.helios import (
    booking_link,
    extract_blob,
    parse_cinema_names,
    parse_repertoire,
    repertoire_url,
)

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = (FIXTURES / "helios_page.html").read_text(encoding="utf-8")

CINEMA = "helios:warszawa/kino-helios-blue-city"
TODAY = "2026-08-09"
HORIZON = 30
DREAM = "555a671f-f857-4752-908a-f357ef284a71"
PLAIN = "d9a94843-1c20-4107-8593-ddc84595a9f8"
REPLAY = "86478a45-cbac-403d-81aa-074600f356d9"

FILM = {"_id": "m1", "title": "Odyseja"}
SCREENING = {
    "timeFrom": "2026-08-09 19:15:00",
    "sourceId": "555a671f",
    "cinemaScreen": {"feature": "Dream"},
    "moviePrint": {"printType": "2D"},
}


def repertoire():
    return json.loads((FIXTURES / "helios_repertoire.json").read_text(encoding="utf-8"))


def parsed(today=TODAY, horizon=HORIZON):
    return parse_repertoire(repertoire(), CINEMA, today, horizon)


def screening(source_id):
    return next(event for event in parsed() if event.id == source_id)


def synthetic(film, raw=SCREENING, day="2026-08-09"):
    return {"list": [film], "screenings": {day: {"m1": {"screenings": [raw]}}}}


def test_blob_is_located_in_the_page():
    assert extract_blob(PAGE).startswith("window.__NUXT__=(function(")


def test_blob_stops_at_the_first_script_end():
    assert extract_blob(PAGE).endswith("));")


def test_page_without_the_blob_yields_nothing():
    assert extract_blob("<html><body>Brak repertuaru</body></html>") is None


def test_unterminated_blob_yields_nothing():
    assert extract_blob("<script>window.__NUXT__=(function(){}") is None


def test_repertoire_url_points_at_the_cinema_page():
    url = repertoire_url("warszawa/kino-helios-blue-city")

    assert url == "https://helios.pl/warszawa/kino-helios-blue-city/repertuar"


def test_booking_link_uses_the_source_id():
    assert booking_link(DREAM) == f"https://bilety.helios.pl/screen/{DREAM}"


def test_parses_every_screening_inside_the_horizon():
    assert len(parsed()) == 42


def test_date_beyond_the_horizon_is_excluded():
    assert "2026-09-27" not in {event.business_day for event in parsed()}


def test_date_inside_a_wider_horizon_is_kept():
    assert "2026-09-27" in {event.business_day for event in parsed(horizon=60)}


def test_date_before_today_is_excluded():
    assert "2026-08-09" not in {event.business_day for event in parsed(today="2026-08-10")}


def test_horizon_edge_day_is_kept():
    assert "2026-08-15" in {event.business_day for event in parsed(horizon=6)}


def test_day_past_the_horizon_edge_is_excluded():
    assert "2026-08-15" not in {event.business_day for event in parsed(horizon=5)}


def test_dream_feature_becomes_a_lowercase_attribute():
    assert "dream" in screening(DREAM).attribute_ids


def test_print_type_becomes_a_lowercase_attribute():
    assert "2d" in screening(DREAM).attribute_ids


def test_empty_feature_adds_no_hall_attribute():
    assert screening(PLAIN).attribute_ids == ("2d",)


def test_missing_print_leaves_no_attributes():
    assert screening(REPLAY).attribute_ids == ()


def test_auditorium_is_the_hall_feature():
    assert screening(DREAM).auditorium == "Dream"


def test_auditorium_is_empty_without_a_feature():
    assert screening(PLAIN).auditorium == ""


def test_business_day_is_the_date_part_of_the_start_time():
    assert screening(DREAM).business_day == "2026-08-09"


def test_date_time_is_written_in_isoformat():
    assert screening(DREAM).date_time == "2026-08-09T19:15:00"


def test_date_time_parses_as_a_datetime():
    assert datetime.fromisoformat(screening(DREAM).date_time).hour == 19


def test_booking_link_is_built_from_the_source_id():
    assert screening(DREAM).booking_link == f"https://bilety.helios.pl/screen/{DREAM}"


def test_film_name_comes_from_the_film_list():
    assert screening(DREAM).film_name == "Tylko jedna noc"


def test_film_id_is_the_screenings_key():
    assert screening(DREAM).film_id == "m4608"


def test_special_event_keeps_its_own_screenings_key():
    assert screening(REPLAY).film_id == "e2674"


def test_special_event_takes_its_name_from_the_film_list():
    assert screening(REPLAY).film_name == "Bodyguard w Helios RePlay"


def test_cinema_id_is_carried_onto_every_event():
    assert {event.cinema_id for event in parsed()} == {CINEMA}


def test_null_title_falls_back_to_the_original_title():
    film = {"_id": "m1", "title": None, "titleOriginal": "The Odyssey", "slug": "odyseja"}

    assert parse_repertoire(synthetic(film), CINEMA, TODAY, HORIZON)[0].film_name == "The Odyssey"


def test_missing_titles_fall_back_to_the_slug():
    film = {"_id": "m1", "title": None, "titleOriginal": None, "slug": "odyseja"}

    assert parse_repertoire(synthetic(film), CINEMA, TODAY, HORIZON)[0].film_name == "odyseja"


def test_film_key_falls_back_to_the_numeric_id():
    film = {"id": 1, "title": "Odyseja"}

    assert parse_repertoire(synthetic(film), CINEMA, TODAY, HORIZON)[0].film_id == "m1"


def test_screening_of_an_unlisted_film_is_skipped():
    assert parse_repertoire(synthetic({"_id": "m2"}), CINEMA, TODAY, HORIZON) == []


def test_screening_without_a_source_id_is_skipped():
    repertoire = synthetic(FILM, {**SCREENING, "sourceId": None})

    assert parse_repertoire(repertoire, CINEMA, TODAY, HORIZON) == []


def test_screening_without_a_start_time_is_skipped():
    repertoire = synthetic(FILM, {**SCREENING, "timeFrom": ""})

    assert parse_repertoire(repertoire, CINEMA, TODAY, HORIZON) == []


def test_repertoire_without_screenings_yields_nothing():
    assert parse_repertoire({"list": []}, CINEMA, TODAY, HORIZON) is None


def test_day_that_is_not_a_mapping_is_skipped():
    broken = {"list": [], "screenings": {"2026-08-09": []}}

    assert parse_repertoire(broken, CINEMA, TODAY, HORIZON) == []


def test_film_group_that_is_not_a_mapping_is_skipped():
    broken = {"list": [FILM], "screenings": {"2026-08-09": {"m1": []}}}

    assert parse_repertoire(broken, CINEMA, TODAY, HORIZON) == []


def test_screening_that_is_not_a_mapping_is_skipped():
    assert parse_repertoire(synthetic(FILM, "seans"), CINEMA, TODAY, HORIZON) == []


def test_cinema_key_joins_the_city_and_the_slug():
    raw = [{"slugCity": "warszawa", "slug": "kino-helios-blue-city", "name": "Blue City"}]

    assert parse_cinema_names(raw) == {"warszawa/kino-helios-blue-city": "Blue City"}


def test_cinema_without_a_name_is_skipped():
    assert parse_cinema_names([{"slugCity": "warszawa", "slug": "kino-helios-blue-city"}]) == {}


def test_cinema_without_a_slug_is_skipped():
    assert parse_cinema_names([{"slugCity": "warszawa", "name": "Blue City"}]) == {}
