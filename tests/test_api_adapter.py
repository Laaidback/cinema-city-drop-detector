from ccdrop.api import CinemaCityApi, FetchOutcome, FetchResult


class StubClient:
    def __init__(self, result):
        self.result = result

    def fetch(self, url, last_modified):
        return self.result

    def throttle(self):
        pass


def test_dates_failure_returns_none():
    api = CinemaCityApi(StubClient(FetchResult(FetchOutcome.FAILED)))

    assert api.fetch_dates("1090", "2026-09-01") is None


def test_dates_success_returns_list():
    payload = {"body": {"dates": ["2026-08-15"]}}
    api = CinemaCityApi(StubClient(FetchResult(FetchOutcome.OK, payload=payload)))

    assert api.fetch_dates("1090", "2026-09-01") == ["2026-08-15"]


def test_cinema_names_failure_returns_empty_dict():
    api = CinemaCityApi(StubClient(FetchResult(FetchOutcome.FAILED)))

    assert api.fetch_cinema_names("2026-09-01") == {}
