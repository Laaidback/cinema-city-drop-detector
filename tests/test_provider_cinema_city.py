from ccdrop.api import CinemaCityProvider, FetchOutcome, FetchResult

TODAY = "2026-08-02"
HORIZON = 30


def ok(payload):
    return FetchResult(FetchOutcome.OK, payload=payload)


def dates(*days):
    return ok({"body": {"dates": list(days)}})


def film_events(*event_ids):
    return ok(
        {
            "body": {
                "films": [{"id": "f1", "name": "Backrooms. Bez wyjścia"}],
                "events": [
                    {
                        "id": event_id,
                        "filmId": "f1",
                        "cinemaId": "1090",
                        "businessDay": "2026-08-15",
                        "eventDateTime": "2026-08-15T18:30:00",
                    }
                    for event_id in event_ids
                ],
            }
        }
    )


class StubClient:
    def __init__(self, dates_result=None, events_by_day=None, names_result=None):
        self.dates_result = dates_result or FetchResult(FetchOutcome.FAILED)
        self.events_by_day = events_by_day or {}
        self.names_result = names_result or FetchResult(FetchOutcome.FAILED)
        self.urls = []
        self.throttles = 0

    def fetch(self, url):
        self.urls.append(url)
        if "/dates/" in url:
            return self.dates_result
        if "/cinemas/" in url:
            return self.names_result
        day = url.split("/at-date/")[1].split("?")[0]
        return self.events_by_day.get(day, FetchResult(FetchOutcome.FAILED))

    def throttle(self):
        self.throttles += 1


def provider(**kwargs):
    return CinemaCityProvider(StubClient(**kwargs))


def test_dates_failure_returns_none():
    assert provider().fetch("cc:1090", TODAY, HORIZON) is None


def test_empty_dates_list_returns_no_events():
    api = provider(dates_result=dates())

    assert api.fetch("cc:1090", TODAY, HORIZON) == []


def test_fetched_date_contributes_its_events():
    api = provider(
        dates_result=dates("2026-08-15"), events_by_day={"2026-08-15": film_events("1")}
    )

    assert [event.id for event in api.fetch("cc:1090", TODAY, HORIZON)] == ["1"]


def test_failed_date_leaves_the_other_dates_events():
    api = provider(
        dates_result=dates("2026-08-15", "2026-08-16"),
        events_by_day={"2026-08-16": film_events("2")},
    )

    assert [event.id for event in api.fetch("cc:1090", TODAY, HORIZON)] == ["2"]


def test_failed_date_does_not_fail_the_cinema():
    api = provider(dates_result=dates("2026-08-15"))

    assert api.fetch("cc:1090", TODAY, HORIZON) == []


def test_event_cinema_id_carries_the_chain_prefix():
    api = provider(
        dates_result=dates("2026-08-15"), events_by_day={"2026-08-15": film_events("1")}
    )

    assert api.fetch("cc:1090", TODAY, HORIZON)[0].cinema_id == "cc:1090"


def test_requested_url_drops_the_chain_prefix():
    client = StubClient(dates_result=dates())
    CinemaCityProvider(client).fetch("cc:1090", TODAY, HORIZON)

    assert "/dates/in-cinema/1090/" in client.urls[0]


def test_dates_url_reaches_the_horizon():
    client = StubClient(dates_result=dates())
    CinemaCityProvider(client).fetch("cc:1090", TODAY, HORIZON)

    assert "/until/2026-09-01" in client.urls[0]


def test_every_request_is_throttled():
    client = StubClient(
        dates_result=dates("2026-08-15", "2026-08-16"),
        events_by_day={"2026-08-15": film_events("1"), "2026-08-16": film_events("2")},
    )
    CinemaCityProvider(client).fetch("cc:1090", TODAY, HORIZON)

    assert client.throttles == 3


def test_cinema_names_failure_returns_empty_dict():
    assert provider().cinema_names(TODAY, HORIZON) == {}


def test_cinema_names_carry_the_chain_prefix():
    names = ok({"body": {"cinemas": [{"id": "1090", "displayName": "Kraków Bonarka"}]}})
    api = provider(names_result=names)

    assert api.cinema_names(TODAY, HORIZON) == {"cc:1090": "Kraków Bonarka"}


def test_cinema_names_request_is_throttled():
    client = StubClient()
    CinemaCityProvider(client).cinema_names(TODAY, HORIZON)

    assert client.throttles == 1
