"""Wypisuje numery i nazwy kin Cinema City do wklejenia w config.yaml."""

import sys
from datetime import date, timedelta

import requests

from ccdrop.api import USER_AGENT, cinemas_url, parse_cinema_names

if __name__ == "__main__":
    needle = sys.argv[1].casefold() if len(sys.argv) > 1 else ""
    until = (date.today() + timedelta(days=30)).isoformat()
    response = requests.get(cinemas_url(until), headers={"User-Agent": USER_AGENT}, timeout=30)
    names = parse_cinema_names(response.json())
    for cinema_id, name in sorted(names.items(), key=lambda kv: kv[1]):
        if needle in name.casefold():
            print(f"{cinema_id}  {name}")
