import re
import unicodedata


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return without_marks.casefold().replace("ł", "l")


def matches(pattern: str, film_name: str) -> bool:
    if len(pattern) >= 2 and pattern.startswith("/") and pattern.endswith("/"):
        return re.search(pattern[1:-1], film_name) is not None
    return normalize(pattern) in normalize(film_name)
