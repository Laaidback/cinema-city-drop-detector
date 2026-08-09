from ccdrop.api import THROTTLE_SECONDS, ApiClient, FetchOutcome


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, dict(headers or {})))
        return self.responses.pop(0)


def client(session):
    return ApiClient(session=session, sleep=lambda _: None)


def test_200_returns_payload():
    session = FakeSession([FakeResponse(200, {"body": {"a": 1}})])

    assert client(session).fetch("http://x").payload == {"body": {"a": 1}}


def test_retries_on_429_then_succeeds():
    session = FakeSession([FakeResponse(429), FakeResponse(200, {"body": {}})])

    assert client(session).fetch("http://x").status is FetchOutcome.OK


def test_gives_up_after_three_attempts():
    session = FakeSession([FakeResponse(500), FakeResponse(500), FakeResponse(500)])

    assert client(session).fetch("http://x").status is FetchOutcome.FAILED


def test_throttle_waits_the_configured_interval():
    delays = []
    ApiClient(session=FakeSession([]), sleep=delays.append).throttle()

    assert delays == [THROTTLE_SECONDS]
