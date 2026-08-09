"""Wypisuje rozkład godzin, w których wykryto nowe seanse.

Czyta drop_log ze stanu i pokazuje, o których porach kina publikują repertuar.
Wynik decyduje, czy zawęzić odpytywanie do okna wokół pełnej godziny.
"""

import collections
import json
import sys
from pathlib import Path

if __name__ == "__main__":
    state_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("state")
    entries = json.loads((state_dir / "seen.json").read_text(encoding="utf-8")).get("drop_log", [])

    if not entries:
        sys.exit("Rejestr pusty — żaden drop nie został jeszcze dostarczony.")

    hours = collections.Counter(e["detected_at"][11:13] for e in entries)
    minutes = collections.Counter(int(e["detected_at"][14:16]) for e in entries)
    films = collections.Counter(e["film"] for e in entries)
    seansow = sum(e["count"] for e in entries)

    print(f"dropów: {len(entries)}, seansów łącznie: {seansow}")
    print(f"zakres: {min(e['detected_at'] for e in entries)[:16]}"
          f" .. {max(e['detected_at'] for e in entries)[:16]}\n")

    print("godzina wykrycia:")
    peak = max(hours.values())
    for h in sorted(hours):
        bar = "█" * max(1, round(hours[h] / peak * 40))
        print(f"  {h}:00  {hours[h]:3}  {bar}")

    near_hour = sum(n for m, n in minutes.items() if m <= 3 or m >= 58)
    print(f"\nw oknie 58-03 wokół pełnej godziny: {near_hour} z {len(entries)}"
          f" ({near_hour * 100 // len(entries)}%)")

    print("\nfilmy:")
    for name, n in films.most_common():
        print(f"  {n:3}x  {name}")
