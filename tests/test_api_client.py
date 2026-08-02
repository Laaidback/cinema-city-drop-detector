import pytest

from ccdrop.api import FetchOutcome, ApiClient


class FakeResponse:
    def __init__(self, status_code, headers=None, payload=None):
        self.status_code = status_code
        self.headers = headers or {}
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


def test_sends_if_modified_since_when_cached():
    session = FakeSession([FakeResponse(304)])
    client(session).fetch("http://x", last_modified="Sat, 01 Aug 2026 21:07:38 GMT")

    assert session.calls[0][1]["If-Modified-Since"] == "Sat, 01 Aug 2026 21:07:38 GMT"


def test_omits_header_without_cache():
    session = FakeSession([FakeResponse(200, {"Last-Modified": "x"}, {"body": {}})])
    client(session).fetch("http://x", last_modified=None)

    assert "If-Modified-Since" not in session.calls[0][1]


def test_304_reports_not_modified():
    session = FakeSession([FakeResponse(304)])

    assert client(session).fetch("http://x", "lm").status is FetchOutcome.NOT_MODIFIED


def test_200_returns_payload():
    session = FakeSession([FakeResponse(200, {"Last-Modified": "x"}, {"body": {"a": 1}})])

    assert client(session).fetch("http://x", None).payload == {"body": {"a": 1}}


def test_retries_on_429_then_succeeds():
    session = FakeSession(
        [FakeResponse(429), FakeResponse(200, {"Last-Modified": "x"}, {"body": {}})]
    )

    assert client(session).fetch("http://x", None).status is FetchOutcome.OK


def test_gives_up_after_three_attempts():
    session = FakeSession([FakeResponse(500), FakeResponse(500), FakeResponse(500)])

    assert client(session).fetch("http://x", None).status is FetchOutcome.FAILED
