"""Fetch Wikipedia's lead summary for each place used in the cards, ONCE, so a person can shorten it in their own words.

  .venv/bin/python scripts/fetch_place_summaries.py            # writes samples/cards/places.raw.json

Standard library only. Never called at runtime and never from a student's browser (student privacy: no third-party requests).
Text from Wikipedia is CC BY-SA; the cards credit it. A place with no Wikipedia page is reported and skipped, never invented.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENDPOINT = "https://en.wikipedia.org/api/rest_v1/page/summary/"
USER_AGENT = "SoundAlongCards/1.0 (one-off content build; no personal data)"
OUT = Path(__file__).resolve().parent.parent / "samples" / "cards" / "places.raw.json"

# place key as it appears in the passage -> exact Wikipedia page title. Fictional places (Pride and Prejudice's Rosings,
# Longbourn, Hunsford as written) are deliberately left out.
PLACES: dict[str, dict[str, str]] = {
    "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98": {
        "Piedmont Park": "Piedmont_Park",
        "Atlanta": "Atlanta",
        "Georgia": "Georgia_(U.S._state)",
    },
    "5af24980-4d6d-41c1-87fa-4f21cb2d169d": {
        "Boston Harbor": "Boston_Harbor",
        "Boston": "Boston",
        "Great Britain": "Great_Britain",
        "England": "England",
        "China": "China",
        "India": "India",
        "North America": "North_America",
    },
    "ff1d34c9-14f1-4e78-b509-6568dc912a17": {
        "Hertfordshire": "Hertfordshire",
        "London": "London",
    },
}


def fetch(title: str) -> dict | None:
    req = urllib.request.Request(ENDPOINT + urllib.parse.quote(title, safe="_()"), headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:  # noqa: S310 (fixed https endpoint)
            data = json.loads(res.read(1_000_000).decode("utf-8"))  # a summary is a few KB; never read an unbounded body
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
        sys.stderr.write(f"  skipped {title}: {err}\n")
        return None
    if data.get("type") != "standard" or not data.get("extract"):
        sys.stderr.write(f"  skipped {title}: not a plain article\n")
        return None
    return {"title": data["title"], "extract": data["extract"]}


def main() -> int:
    out = {}
    for passage_id, places in PLACES.items():
        out[passage_id] = {}
        for key, title in places.items():
            got = fetch(title)
            if got:
                out[passage_id][key] = got
                print(f"{key}: {got['extract'][:110]}...")
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
