import dataclasses

import pytest

from ccdrop.models import Event, State, WatchState


class FakeProvider:
    def __init__(self, events_by_date, failed_dates, dates_fail):
        self.events_by_date = events_by_date
        self.failed_dates = set(failed_dates)
        self.dates_fail = dates_fail

    def cinema_names(self, today, horizon_days):
        return {"cc:1090": "Kraków Bonarka"}

    def fetch(self, cinema_id, today, horizon_days):
        if self.dates_fail:
            return None
        return [
            Event(
                id=eid,
                film_id="f1",
                film_name="Backrooms. Bez wyjścia",
                cinema_id=cinema_id,
                business_day=business_day,
                date_time=f"{business_day}T18:30:00",
                auditorium="Sala 4",
                booking_link=f"https://tickets.cinema-city.pl/api/order/{eid}",
                attribute_ids=("imax",),
            )
            for day in sorted(self.events_by_date)
            if day not in self.failed_dates
            for eid, business_day in self.events_by_date[day]
        ]


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
    providers: dict
    notifier: FakeNotifier


@pytest.fixture
def fake_world():
    def build(warm, events=(), send_ok=True, failed_dates=(), dates_fail=False, fail_from=None):
        events_by_date = {}
        for event_id, business_day in events:
            events_by_date.setdefault(business_day, []).append((event_id, business_day))
        state = State()
        if warm:
            state.watch_state["Backrooms|cc:1090"] = WatchState(warm=True, seen_events={})
        return World(
            state=state,
            providers={"cc": FakeProvider(events_by_date, failed_dates, dates_fail)},
            notifier=FakeNotifier(send_ok, fail_from),
        )

    return build


@pytest.fixture(autouse=True)
def instant_part_delay(monkeypatch):
    monkeypatch.setattr("ccdrop.main.PART_INTERVAL_SECONDS", 0)
