import logging
import time
from dataclasses import dataclass
from enum import Enum

import requests

from ccdrop.models import Event

BASE = "https://www.cinema-city.pl/pl/data-api-service/v1/quickbook/10103"
QUERY = "?attr=&lang=pl_PL"
USER_AGENT = "ccdrop/0.1 (+https://github.com/Laaidback/cinema-city-drop-detector)"
MAX_ATTEMPTS = 3
THROTTLE_SECONDS = 0.2

log = logging.getLogger("ccdrop")


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


class FetchOutcome(Enum):
    OK = "ok"
    NOT_MODIFIED = "not_modified"
    FAILED = "failed"


@dataclass(frozen=True)
class FetchResult:
    status: FetchOutcome
    payload: dict | None = None
    last_modified: str | None = None


class ApiClient:
    def __init__(self, session=None, sleep=time.sleep):
        self.session = session or requests.Session()
        self.sleep = sleep

    def fetch(self, url: str, last_modified: str | None) -> FetchResult:
        headers = {"User-Agent": USER_AGENT}
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self.session.get(url, headers=headers, timeout=30)
            except requests.RequestException:
                self.sleep(2**attempt)
                continue

            log.debug("%s -> HTTP %s", url, response.status_code)

            if response.status_code == 304:
                return FetchResult(FetchOutcome.NOT_MODIFIED)
            if response.status_code == 200:
                return FetchResult(
                    FetchOutcome.OK,
                    payload=response.json(),
                    last_modified=response.headers.get("Last-Modified"),
                )
            if response.status_code == 429 or response.status_code >= 500:
                self.sleep(2**attempt)
                continue
            return FetchResult(FetchOutcome.FAILED)

        return FetchResult(FetchOutcome.FAILED)

    def throttle(self) -> None:
        self.sleep(THROTTLE_SECONDS)


class CinemaCityApi:
    def __init__(self, client: ApiClient):
        self.client = client

    def fetch_cinema_names(self, until: str) -> dict[str, str]:
        result = self.client.fetch(cinemas_url(until), None)
        self.client.throttle()
        if result.status is not FetchOutcome.OK:
            log.warning("Nie udało się pobrać nazw kin — powiadomienia pokażą numery")
            return {}
        return parse_cinema_names(result.payload)

    def fetch_dates(self, cinema_id: str, until: str) -> list[str] | None:
        result = self.client.fetch(dates_url(cinema_id, until), None)
        self.client.throttle()
        if result.status is not FetchOutcome.OK:
            log.warning("Brak listy dat dla kina %s — kino pominięte w tym cyklu", cinema_id)
            return None
        return parse_dates(result.payload)

    def fetch_events(self, cinema_id: str, day: str, last_modified: str | None):
        result = self.client.fetch(events_url(cinema_id, day), last_modified)
        self.client.throttle()
        log.debug("kino %s dzień %s -> %s", cinema_id, day, result.status.value)
        return result
