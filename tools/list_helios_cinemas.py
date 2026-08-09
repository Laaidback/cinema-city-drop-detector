"""Wypisuje identyfikatory i nazwy kin Helios do wklejenia w config.yaml."""

import sys

from ccdrop.chains import prefixed
from ccdrop.helios import (
    CINEMAS_PATH,
    HOME_URL,
    HeliosProvider,
    PageClient,
    QjsEvaluator,
    nuxt_state,
    parse_cinema_names,
)

if __name__ == "__main__":
    needle = sys.argv[1].casefold() if len(sys.argv) > 1 else ""
    cinemas = nuxt_state(PageClient(), QjsEvaluator(), HOME_URL, CINEMAS_PATH)
    names = parse_cinema_names(cinemas if isinstance(cinemas, list) else [])
    for cinema, name in sorted(names.items(), key=lambda kv: kv[1]):
        if needle in name.casefold():
            print(f"{prefixed(HeliosProvider.chain, cinema)}  {name}")
