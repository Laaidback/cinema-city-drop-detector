import json
import logging
import subprocess
import tempfile
from pathlib import Path

import requests

from ccdrop.api import horizon_date
from ccdrop.chains import local_id, prefixed
from ccdrop.models import Event

BASE = "https://helios.pl"
HOME_URL = f"{BASE}/"
BOOKING_BASE = "https://bilety.helios.pl/screen"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
BLOB_MARKER = "window.__NUXT__"
SCRIPT_END = "</script>"
REPERTOIRE_PATH = "state.repertoire"
CINEMAS_PATH = "state.core.cinemas"
QJS_BINARY = "qjs"
QJS_TIMEOUT_SECONDS = 30

log = logging.getLogger("ccdrop")


def repertoire_url(cinema: str) -> str:
    return f"{BASE}/{cinema}/repertuar"


def booking_link(source_id: str) -> str:
    return f"{BOOKING_BASE}/{source_id}"


def extract_blob(html: str) -> str | None:
    start = html.find(BLOB_MARKER)
    if start < 0:
        return None
    end = html.find(SCRIPT_END, start)
    if end < 0:
        return None
    return html[start:end]


def film_titles(films) -> dict[str, str]:
    titles = {}
    for film in films or ():
        key = film.get("_id") or f"m{film.get('id')}"
        title = film.get("title") or film.get("titleOriginal") or film.get("slug")
        if title:
            titles[key] = str(title)
    return titles


def parse_screening(raw, film_id: str, film_name: str, cinema_id: str) -> Event | None:
    if not isinstance(raw, dict):
        return None

    source_id = raw.get("sourceId")
    day, _, clock = (raw.get("timeFrom") or "").partition(" ")
    if not source_id or not clock:
        return None

    feature = (raw.get("cinemaScreen") or {}).get("feature") or ""
    print_type = (raw.get("moviePrint") or {}).get("printType") or ""
    return Event(
        id=str(source_id),
        film_id=film_id,
        film_name=film_name,
        cinema_id=cinema_id,
        business_day=day,
        date_time=f"{day}T{clock}",
        auditorium=feature,
        booking_link=booking_link(str(source_id)),
        attribute_ids=tuple(value.lower() for value in (feature, print_type) if value),
    )


def parse_repertoire(
    repertoire, cinema_id: str, today: str, horizon_days: int
) -> list[Event] | None:
    screenings = repertoire.get("screenings")
    if not isinstance(screenings, dict):
        log.warning("Helios: repertuar kina %s bez mapy screenings", cinema_id)
        return None

    titles = film_titles(repertoire.get("list"))
    until = horizon_date(today, horizon_days)
    events: list[Event] = []

    for day in sorted(screenings):
        if not today <= day <= until:
            continue
        films = screenings[day]
        if not isinstance(films, dict):
            log.warning("Helios: dzień %s w kinie %s ma nieznany kształt", day, cinema_id)
            continue
        for film_id, group in films.items():
            film_name = titles.get(film_id)
            if film_name is None:
                log.warning("Helios: film %s spoza listy filmów, seanse pominięte", film_id)
                continue
            if not isinstance(group, dict):
                log.warning("Helios: film %s ma nieznany kształt seansów", film_id)
                continue
            for raw in group.get("screenings") or ():
                event = parse_screening(raw, film_id, film_name, cinema_id)
                if event is not None:
                    events.append(event)

    return events


def parse_cinema_names(cinemas) -> dict[str, str]:
    names = {}
    for cinema in cinemas or ():
        city = cinema.get("slugCity")
        slug = cinema.get("slug")
        name = cinema.get("name")
        if city and slug and name:
            names[f"{city}/{slug}"] = str(name)
    return names


class PageClient:
    def __init__(self, session=None):
        self.session = session or requests.Session()

    def get(self, url: str) -> str | None:
        try:
            response = self.session.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        except requests.RequestException as failure:
            log.warning("Helios: %s nieosiągalne (%s)", url, failure)
            return None

        log.debug("%s -> HTTP %s", url, response.status_code)
        if response.status_code != 200:
            log.warning("Helios: %s -> HTTP %s", url, response.status_code)
            return None
        return response.text


class QjsEvaluator:
    def __init__(self, binary: str = QJS_BINARY, timeout: int = QJS_TIMEOUT_SECONDS):
        self.binary = binary
        self.timeout = timeout

    def evaluate(self, blob: str, path: str):
        script = f"var window={{}};{blob}\nprint(JSON.stringify({BLOB_MARKER}.{path}));"
        with tempfile.TemporaryDirectory() as directory:
            script_file = Path(directory) / "nuxt.js"
            script_file.write_text(script, encoding="utf-8")
            try:
                done = subprocess.run(
                    [self.binary, str(script_file)],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
            except (OSError, subprocess.SubprocessError) as failure:
                log.warning("Helios: nie udało się uruchomić %s (%s)", self.binary, failure)
                return None

        if done.returncode != 0:
            log.warning("Helios: %s zakończone błędem: %s", self.binary, done.stderr.strip())
            return None

        try:
            return json.loads(done.stdout)
        except json.JSONDecodeError:
            log.warning("Helios: %s nie zwrócił JSON-a dla %s", self.binary, path)
            return None


def nuxt_state(client: PageClient, evaluator: QjsEvaluator, url: str, path: str):
    html = client.get(url)
    if html is None:
        return None

    blob = extract_blob(html)
    if blob is None:
        log.warning("Helios: brak %s na stronie %s", BLOB_MARKER, url)
        return None

    return evaluator.evaluate(blob, path)


class HeliosProvider:
    chain = "helios"

    def __init__(self, client: PageClient, evaluator: QjsEvaluator):
        self.client = client
        self.evaluator = evaluator

    def cinema_names(self, today: str, horizon_days: int) -> dict[str, str]:
        cinemas = nuxt_state(self.client, self.evaluator, HOME_URL, CINEMAS_PATH)
        if not isinstance(cinemas, list):
            log.warning("Helios: brak listy kin — powiadomienia pokażą identyfikatory")
            return {}
        return {
            prefixed(self.chain, cinema): name
            for cinema, name in parse_cinema_names(cinemas).items()
        }

    def fetch(self, cinema_id: str, today: str, horizon_days: int) -> list[Event] | None:
        cinema = local_id(cinema_id)
        url = repertoire_url(cinema)
        repertoire = nuxt_state(self.client, self.evaluator, url, REPERTOIRE_PATH)
        if not isinstance(repertoire, dict):
            log.warning("Helios: brak repertuaru kina %s — pominięte w tym cyklu", cinema_id)
            return None
        return parse_repertoire(repertoire, prefixed(self.chain, cinema), today, horizon_days)
