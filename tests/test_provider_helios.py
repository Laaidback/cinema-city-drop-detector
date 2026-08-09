import json
import subprocess
from pathlib import Path

import requests

from ccdrop import helios
from ccdrop.helios import (
    CINEMAS_PATH,
    HOME_URL,
    REPERTOIRE_PATH,
    HeliosProvider,
    PageClient,
    QjsEvaluator,
)
from ccdrop.providers import PROVIDERS, build_providers

CINEMA = "helios:warszawa/kino-helios-blue-city"
CINEMA_URL = "https://helios.pl/warszawa/kino-helios-blue-city/repertuar"
TODAY = "2026-08-09"
HORIZON = 30
PAGE = "<script>window.__NUXT__=(function(){return 1}());</script>"
BLOB = "window.__NUXT__=(function(){return 1}());"

REPERTOIRE = {
    "list": [{"_id": "m4608", "title": "Tylko jedna noc"}],
    "screenings": {
        "2026-08-09": {
            "m4608": {
                "screenings": [
                    {
                        "timeFrom": "2026-08-09 19:15:00",
                        "sourceId": "555a671f",
                        "cinemaScreen": {"feature": "Dream"},
                        "moviePrint": {"printType": "2D"},
                    }
                ]
            }
        }
    },
}

CINEMAS = [{"slugCity": "warszawa", "slug": "kino-helios-blue-city", "name": "Blue City"}]


class StubClient:
    def __init__(self, pages=None):
        self.pages = pages or {}
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return self.pages.get(url)


class StubEvaluator:
    def __init__(self, value=None):
        self.value = value
        self.calls = []

    def evaluate(self, blob, path):
        self.calls.append((blob, path))
        return self.value


class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, dict(headers or {})))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeRun:
    def __init__(self, returncode=0, stdout="", stderr="", raising=None):
        self.result = subprocess.CompletedProcess([], returncode, stdout, stderr)
        self.raising = raising
        self.commands = []
        self.timeouts = []
        self.scripts = []

    def __call__(self, command, capture_output=None, text=None, timeout=None):
        self.commands.append(command)
        self.timeouts.append(timeout)
        self.scripts.append(Path(command[-1]).read_text(encoding="utf-8"))
        if self.raising is not None:
            raise self.raising
        return self.result


def provider(pages=None, value=None):
    return HeliosProvider(StubClient(pages), StubEvaluator(value))


def evaluator(monkeypatch, run, **kwargs):
    monkeypatch.setattr(helios.subprocess, "run", run)
    return QjsEvaluator(**kwargs)


def test_http_failure_yields_no_events():
    assert provider().fetch(CINEMA, TODAY, HORIZON) is None


def test_page_without_the_blob_yields_no_events():
    api = provider(pages={CINEMA_URL: "<html><body>Brak</body></html>"})

    assert api.fetch(CINEMA, TODAY, HORIZON) is None


def test_qjs_failure_yields_no_events():
    assert provider(pages={CINEMA_URL: PAGE}, value=None).fetch(CINEMA, TODAY, HORIZON) is None


def test_unexpected_repertoire_shape_yields_no_events():
    api = provider(pages={CINEMA_URL: PAGE}, value=["nie", "obiekt"])

    assert api.fetch(CINEMA, TODAY, HORIZON) is None


def test_screening_becomes_an_event():
    api = provider(pages={CINEMA_URL: PAGE}, value=REPERTOIRE)

    assert [event.id for event in api.fetch(CINEMA, TODAY, HORIZON)] == ["555a671f"]


def test_event_cinema_id_carries_the_chain_prefix():
    api = provider(pages={CINEMA_URL: PAGE}, value=REPERTOIRE)

    assert api.fetch(CINEMA, TODAY, HORIZON)[0].cinema_id == CINEMA


def test_requested_page_drops_the_chain_prefix():
    client = StubClient({CINEMA_URL: PAGE})
    HeliosProvider(client, StubEvaluator(REPERTOIRE)).fetch(CINEMA, TODAY, HORIZON)

    assert client.urls == [CINEMA_URL]


def test_repertoire_is_read_from_the_repertoire_state():
    stub = StubEvaluator(REPERTOIRE)
    HeliosProvider(StubClient({CINEMA_URL: PAGE}), stub).fetch(CINEMA, TODAY, HORIZON)

    assert stub.calls[0][1] == REPERTOIRE_PATH


def test_only_the_page_blob_is_evaluated():
    stub = StubEvaluator(REPERTOIRE)
    HeliosProvider(StubClient({CINEMA_URL: PAGE}), stub).fetch(CINEMA, TODAY, HORIZON)

    assert stub.calls[0][0] == BLOB


def test_cinema_names_carry_the_chain_prefix():
    api = provider(pages={HOME_URL: PAGE}, value=CINEMAS)

    assert api.cinema_names(TODAY, HORIZON) == {CINEMA: "Blue City"}


def test_cinema_names_are_read_from_the_cinema_list_state():
    stub = StubEvaluator(CINEMAS)
    HeliosProvider(StubClient({HOME_URL: PAGE}), stub).cinema_names(TODAY, HORIZON)

    assert stub.calls[0][1] == CINEMAS_PATH


def test_cinema_names_failure_returns_empty_dict():
    assert provider().cinema_names(TODAY, HORIZON) == {}


def test_unexpected_cinema_list_returns_empty_dict():
    api = provider(pages={HOME_URL: PAGE}, value={"nie": "lista"})

    assert api.cinema_names(TODAY, HORIZON) == {}


def test_page_client_returns_the_body():
    session = FakeSession([FakeResponse(200, "<html></html>")])

    assert PageClient(session).get("http://x") == "<html></html>"


def test_page_client_sends_a_browser_user_agent():
    session = FakeSession([FakeResponse(200)])
    PageClient(session).get("http://x")

    assert session.calls[0][1]["User-Agent"].startswith("Mozilla/5.0")


def test_page_client_returns_nothing_on_an_error_status():
    session = FakeSession([FakeResponse(403)])

    assert PageClient(session).get("http://x") is None


def test_page_client_returns_nothing_on_a_network_error():
    session = FakeSession([requests.RequestException("brak sieci")])

    assert PageClient(session).get("http://x") is None


def test_evaluator_returns_the_decoded_output(monkeypatch):
    run = FakeRun(stdout=json.dumps({"list": []}))

    assert evaluator(monkeypatch, run).evaluate(BLOB, REPERTOIRE_PATH) == {"list": []}


def test_evaluator_wraps_the_blob_for_qjs(monkeypatch):
    run = FakeRun(stdout="{}")
    evaluator(monkeypatch, run).evaluate(BLOB, REPERTOIRE_PATH)
    expected = f"var window={{}};{BLOB}\nprint(JSON.stringify(window.__NUXT__.{REPERTOIRE_PATH}));"

    assert run.scripts == [expected]


def test_evaluator_runs_the_configured_binary(monkeypatch):
    run = FakeRun(stdout="{}")
    evaluator(monkeypatch, run, binary="/usr/bin/qjs").evaluate(BLOB, REPERTOIRE_PATH)

    assert run.commands[0][0] == "/usr/bin/qjs"


def test_evaluator_passes_its_timeout_to_the_subprocess(monkeypatch):
    run = FakeRun(stdout="{}")
    evaluator(monkeypatch, run, timeout=7).evaluate(BLOB, REPERTOIRE_PATH)

    assert run.timeouts == [7]


def test_evaluator_returns_nothing_on_a_non_zero_exit(monkeypatch):
    run = FakeRun(returncode=1, stderr="SyntaxError")

    assert evaluator(monkeypatch, run).evaluate(BLOB, REPERTOIRE_PATH) is None


def test_evaluator_returns_nothing_on_a_timeout(monkeypatch):
    run = FakeRun(raising=subprocess.TimeoutExpired("qjs", 30))

    assert evaluator(monkeypatch, run).evaluate(BLOB, REPERTOIRE_PATH) is None


def test_evaluator_returns_nothing_when_the_binary_is_missing(monkeypatch):
    run = FakeRun(raising=FileNotFoundError("qjs"))

    assert evaluator(monkeypatch, run).evaluate(BLOB, REPERTOIRE_PATH) is None


def test_evaluator_returns_nothing_on_unparseable_output(monkeypatch):
    run = FakeRun(stdout="undefined")

    assert evaluator(monkeypatch, run).evaluate(BLOB, REPERTOIRE_PATH) is None


def test_evaluator_leaves_no_script_behind(monkeypatch):
    run = FakeRun(stdout="{}")
    evaluator(monkeypatch, run).evaluate(BLOB, REPERTOIRE_PATH)

    assert not Path(run.commands[0][-1]).exists()


def test_helios_chain_is_registered():
    assert HeliosProvider.chain in PROVIDERS


def test_registered_helios_provider_is_built():
    assert isinstance(build_providers()[HeliosProvider.chain], HeliosProvider)
