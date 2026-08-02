from ccdrop.models import Event

BASE = "https://www.cinema-city.pl/pl/data-api-service/v1/quickbook/10103"
QUERY = "?attr=&lang=pl_PL"


def cinemas_url(until: str) -> str:
    return f"{BASE}/cinemas/with-event/until/{until}{QUERY}"


def dates_url(cinema_id: str, until: str) -> str:
    return f"{BASE}/dates/in-cinema/{cinema_id}/until/{until}{QUERY}"


def events_url(cinema_id: str, date: str) -> str:
    return f"{BASE}/film-events/in-cinema/{cinema_id}/at-date/{date}{QUERY}"


def parse_film_events(payload: dict) -> list[Event]:
    body = payload.get("body", {})
    names = {f["id"]: f["name"] for f in body.get("films", [])}
    events = []
    for raw in body.get("events", []):
        film_id = raw.get("filmId")
        if film_id not in names:
            continue
        try:
            events.append(
                Event(
                    id=str(raw["id"]),
                    film_id=film_id,
                    film_name=names[film_id],
                    cinema_id=str(raw["cinemaId"]),
                    business_day=raw["businessDay"],
                    date_time=raw["eventDateTime"],
                    auditorium=raw.get("auditorium", ""),
                    booking_link=raw.get("bookingLink", ""),
                    attribute_ids=tuple(raw.get("attributeIds", [])),
                )
            )
        except KeyError:
            continue
    return events


def parse_dates(payload: dict) -> list[str]:
    return list(payload.get("body", {}).get("dates", []))


def parse_cinema_names(payload: dict) -> dict[str, str]:
    return {str(c["id"]): c["displayName"] for c in payload.get("body", {}).get("cinemas", [])}
