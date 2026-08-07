from datetime import datetime

import requests

from ccdrop.models import Drop, Event

BUDGET = 3500
WEEKDAYS = ("pn", "wt", "śr", "cz", "pt", "sb", "nd")
ATTRIBUTE_LABELS = {
    "imax": "IMAX",
    "4dx": "4DX",
    "screenx": "ScreenX",
    "dolby-cinema": "Dolby Cinema",
    "vip": "VIP",
    "3d": "3D",
}


def plural_screenings(count: int) -> str:
    if count == 1:
        return "1 nowy seans"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return f"{count} nowe seanse"
    return f"{count} nowych seansów"


def event_row(event: Event) -> str:
    moment = datetime.fromisoformat(event.date_time)
    stamp = f"{WEEKDAYS[moment.weekday()]} {moment:%d.%m}  {moment:%H:%M}"
    labels = [ATTRIBUTE_LABELS[a] for a in event.attribute_ids if a in ATTRIBUTE_LABELS]
    room = " · ".join([event.auditorium, *labels])
    return f"  {stamp}  {room}  {event.booking_link}"


def header(drop: Drop, cinema: str, part: int, parts: int) -> str:
    marker = f"  ({part}/{parts})" if parts > 1 else ""
    return "\n".join(
        [
            f"🎬 {drop.film_name}{marker}",
            f"📍 {cinema} · {plural_screenings(len(drop.events))}",
            "",
        ]
    )


def split_rows(rows: list[str], header_length: int) -> list[list[str]]:
    groups: list[list[str]] = [[]]
    used = header_length
    for row in rows:
        if groups[-1] and used + len(row) + 1 > BUDGET:
            groups.append([])
            used = header_length
        groups[-1].append(row)
        used += len(row) + 1
    return groups


def format_drop(drop: Drop, cinema_names: dict[str, str]) -> list[str]:
    cinema = cinema_names.get(drop.cinema_id, drop.cinema_id)
    rows = [event_row(event) for event in drop.events]

    parts = 1
    while True:
        groups = split_rows(rows, len(header(drop, cinema, parts, parts)))
        if len(groups) <= parts:
            break
        parts = len(groups)

    return [
        "\n".join([header(drop, cinema, index, parts), *group])
        for index, group in enumerate(groups, start=1)
    ]


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, session=None):
        self.token = token
        self.chat_id = chat_id
        self.session = session or requests.Session()

    def send(self, text: str) -> bool:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}
        try:
            response = self.session.post(url, json=payload, timeout=30)
        except requests.RequestException:
            return False
        return response.status_code == 200
