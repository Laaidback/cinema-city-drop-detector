from datetime import datetime

import requests

from ccdrop.models import Drop

MAX_ROWS = 15
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


def format_drop(drop: Drop, cinema_names: dict[str, str]) -> str:
    cinema = cinema_names.get(drop.cinema_id, drop.cinema_id)
    lines = [
        f"🎬 {drop.film_name}",
        f"📍 {cinema} · {plural_screenings(len(drop.events))}",
        "",
    ]

    for event in drop.events[:MAX_ROWS]:
        moment = datetime.fromisoformat(event.date_time)
        stamp = f"{WEEKDAYS[moment.weekday()]} {moment:%d.%m}  {moment:%H:%M}"
        labels = [ATTRIBUTE_LABELS[a] for a in event.attribute_ids if a in ATTRIBUTE_LABELS]
        room = " · ".join([event.auditorium, *labels])
        lines.append(f"  {stamp}  {room}  {event.booking_link}")

    hidden = len(drop.events) - MAX_ROWS
    if hidden > 0:
        lines.append(f"  …i {hidden} więcej")

    return "\n".join(lines)


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
