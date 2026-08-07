import dataclasses

import pytest

from ccdrop.api import FetchOutcome, FetchResult
from ccdrop.models import State, WatchState


class FakeApi:
    def __init__(self, events_by_date, failed_dates, dates_fail):
        self.events_by_date = events_by_date
        self.failed_dates = set(failed_dates)
        self.dates_fail = dates_fail

    def fetch_cinema_names(self, until):
        return {"1090": "Kraków Bonarka"}

    def fetch_dates(self, cinema_id, until):
        if self.dates_fail:
            return None
        return sorted(set(self.events_by_date) | self.failed_dates)

    def fetch_events(self, cinema_id, day):
        if day in self.failed_dates:
            return FetchResult(FetchOutcome.FAILED)
        raw = [
            {
                "id": eid,
                "filmId": "f1",
                "cinemaId": cinema_id,
                "businessDay": business_day,
                "eventDateTime": f"{business_day}T18:30:00",
                "auditorium": "Sala 4",
                "bookingLink": f"https://tickets.cinema-city.pl/api/order/{eid}",
                "attributeIds": ["imax"],
            }
            for eid, business_day in self.events_by_date.get(day, [])
        ]
        payload = {
            "body": {"films": [{"id": "f1", "name": "Backrooms. Bez wyjścia"}], "events": raw}
        }
        return FetchResult(FetchOutcome.OK, payload=payload)


class FakeNotifier:
    def __init__(self, ok, fail_from=None):
        self.ok = ok
        self.fail_from = fail_from
        self.sent = []

    def send(self, text):
        self.sent.append(text)
        if self.fail_from is not None and len(self.sent) >= self.fail_from:
            return False
        return self.ok


@dataclasses.dataclass
class World:
    state: State
    api: FakeApi
    notifier: FakeNotifier


@pytest.fixture
def fake_world():
    def build(warm, events=(), send_ok=True, failed_dates=(), dates_fail=False, fail_from=None):
        events_by_date = {}
        for event_id, business_day in events:
            events_by_date.setdefault(business_day, []).append((event_id, business_day))
        state = State()
        if warm:
            state.watch_state["Backrooms|1090"] = WatchState(warm=True, seen_events={})
        return World(
            state=state,
            api=FakeApi(events_by_date, failed_dates, dates_fail),
            notifier=FakeNotifier(send_ok, fail_from),
        )

    return build


@pytest.fixture(autouse=True)
def instant_part_delay(monkeypatch):
    monkeypatch.setattr("ccdrop.main.PART_INTERVAL_SECONDS", 0)
