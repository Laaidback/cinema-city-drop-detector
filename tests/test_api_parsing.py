import json
from pathlib import Path

from ccdrop.api import events_url, parse_film_events

FIXTURE = Path(__file__).parent / "fixtures" / "film_events_1090.json"


def test_events_url_contains_cinema_and_date():
    url = events_url("1090", "2026-08-15")

    assert "/film-events/in-cinema/1090/at-date/2026-08-15" in url


def test_parses_all_events():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert len(parse_film_events(payload)) == len(payload["body"]["events"])


def test_joins_film_name_from_films_list():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    first = parse_film_events(payload)[0]
    expected = next(f["name"] for f in payload["body"]["films"] if f["id"] == first.film_id)

    assert first.film_name == expected


def test_skips_event_with_unknown_film():
    payload = {"body": {"films": [], "events": [{"id": "1", "filmId": "brak"}]}}

    assert parse_film_events(payload) == []
