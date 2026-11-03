"""Pictures for the place cards, chosen and stored AHEAD of time. Standard library only.

  .venv/bin/python scripts/place_images.py fetch   # slow, polite, cached: find a free-licensed photo per place, download a small thumbnail
  .venv/bin/python scripts/place_images.py apply   # offline: copy the CURATED images into samples/cards/images and write them into the cards

Why this shape (see docs/PLACE_IMAGES.md):
  * Privacy: a student's browser never calls Wikipedia or anyone else. Images are small files on our own origin (/data/...).
  * Cost: one ~50 KB thumbnail per place, delivered by CloudFront from S3. Nothing is generated or fetched while a student reads.
  * Licences: only CC0, public domain, CC BY and CC BY-SA. Every picture carries its author and licence as a visible credit.
  * Safety: only real JPEG or PNG bytes are kept (never SVG), a person looks at each image and writes its alt text, and a place
    with no suitable picture simply has none (imageUrl null).
`fetch` writes candidates to samples/cards/images.candidates/ (not committed). A person reviews them and lists the accepted
ones in samples/cards/images.json with alt text written from what the picture really shows; `apply` reads only that file.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "synth"))
from place_media import (  # noqa: E402  (shared with the live publish step)
    image_size, MAX_ALT, MAX_BYTES, NAME_PATTERN, PACE_SECONDS, THUMB_WIDTH, USER_AGENT, alt_problem, clean_artist, credit_line, image_ext, license_ok, slug, target_name,
)

CARDS = Path(__file__).resolve().parent.parent / "samples" / "cards"

# ---- apply (offline) -------------------------------------------------------------------------------------------------------------
def apply(cards: Path = CARDS) -> list[str]:
    """Write the curated images into samples/cards/images and the three image fields into every cards file. Returns file names."""
    manifest = json.loads((cards / "images.json").read_text(encoding="utf-8")) if (cards / "images.json").exists() else {"images": []}
    chosen: dict[tuple[str, str], dict[str, str]] = {}
    files: dict[str, bytes] = {}
    for entry in manifest.get("images", []):
        data = (cards / "images.candidates" / entry["candidate"]).read_bytes()
        if image_ext(data) is None:
            raise ValueError(f"{entry['candidate']}: not a JPEG or PNG image")
        if not license_ok(entry.get("license")):
            raise ValueError(f"{entry['candidate']}: licence {entry.get('license')!r} is not allowed (CC0, public domain, CC BY, CC BY-SA only)")
        problem = alt_problem(entry.get("alt"), entry["place"])
        if problem:
            raise ValueError(f"{entry['place']}: {problem}")
        name = target_name(entry["passageId"], entry["place"], data)
        files[name] = data
        chosen[(entry["passageId"], entry["place"])] = {
            "imageUrl": f"/data/{name}", "imageAlt": entry["alt"].strip(),
            "imageCredit": credit_line(clean_artist(entry.get("artist")), entry["license"].strip(), "Image" if entry.get("map") else None),
        }

    images = cards / "images"
    images.mkdir(exist_ok=True)
    sizes = {name: image_size(data) for name, data in files.items()}
    for key, card in chosen.items():
        name = card["imageUrl"].removeprefix("/data/")
        card["imageWidth"], card["imageHeight"] = sizes[name] or (None, None)
    for stale in images.iterdir():
        if stale.is_file() and stale.name not in files:
            stale.unlink()
    for name, data in files.items():
        (images / name).write_bytes(data)

    for path in sorted(cards.glob("*.cards.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        passage_id = path.name.removesuffix(".cards.json")
        places = {
            key: {**place, **{"imageUrl": None, "imageAlt": None, "imageCredit": None, "imageWidth": None, "imageHeight": None}, **chosen.get((passage_id, key), {})}
            for key, place in document.get("places", {}).items()
        }
        path.write_text(json.dumps({**document, "places": places}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return sorted(files)


# ---- fetch (network, slow on purpose) --------------------------------------------------------------------------------------------
def _get(url: str, binary: bool = False, cache: dict | None = None):
    if cache is not None and not binary and url in cache:
        return cache[url]
    for attempt in range(4):
        time.sleep(PACE_SECONDS)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=30) as res:  # noqa: S310 (fixed Wikimedia https hosts)
                body = res.read(MAX_BYTES + 1 if binary else 1_000_000)
        except urllib.error.HTTPError as err:
            if err.code == 429 and attempt < 3:
                wait = int(err.headers.get("Retry-After") or 10 * (attempt + 1))
                sys.stderr.write(f"  rate limited; waiting {wait}s\n")
                time.sleep(wait)
                continue
            raise
        if binary:
            if len(body) > MAX_BYTES:
                raise ValueError("image is larger than the size cap")
            return body
        value = json.loads(body.decode("utf-8"))
        if cache is not None:
            cache[url] = value
        return value
    raise RuntimeError("unreachable")


def fetch(cards: Path = CARDS) -> None:
    """Candidates for every place in the demo texts, chosen by the SAME chain the live publish step uses (lead picture, then the article's
    other pictures; photos before maps; never flags). Written to samples/cards/images.candidates/ for a person to look at."""
    import enrich_places as ep
    from fetch_place_summaries import PLACES

    out_dir = cards / "images.candidates"
    out_dir.mkdir(exist_ok=True)
    report = []

    def polite(url: str, binary: bool = False):
        time.sleep(PACE_SECONDS)
        return ep.fetch(url, binary)

    for passage_id, places in PLACES.items():
        reply = polite(ep._query(ep.WIKIPEDIA, redirects="1", titles="|".join(places.values()), prop="coordinates|pageprops|description|pageimages",
                                 colimit="max", piprop="name", ppprop="disambiguation"))
        by_title = {p.get("title"): p for p in ep._pages(reply).values()}
        pages = {}
        for place, title in places.items():
            page = by_title.get(ep._resolve(title.replace("_", " "), reply.get("query", {})))
            if page and not isinstance(page.get("description"), str):
                page = {**page, "description": ""}
            if page:
                pages[place] = {**page, "description": page.get("description") or place}
        found, images, sources = ep._pictures(pages, passage_id, polite, lambda: False)
        for place in places:
            row = {"passageId": passage_id, "place": place}
            if place in found:
                data = next(b for n, b in images.items() if n == found[place]["imageUrl"].removeprefix("/data/"))
                candidate = f"{slug(place)}.{image_ext(data)}"
                (out_dir / candidate).write_bytes(data)
                report.append({**row, "candidate": candidate, "bytes": len(data), "autoAlt": found[place]["imageAlt"], **sources[place]})
                print(f"{place:14} {sources[place]['license']:14} {len(data) // 1024:>4} KB  {candidate}  <- {sources[place]['file'][:50]}")
            else:
                report.append({**row, "rejected": "nothing usable in the whole article"})
                print(f"{place:14} NO PICTURE FOUND")
    (cards / "images.candidates.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n{sum(1 for r in report if 'candidate' in r)} of {len(report)} places have a candidate. Open them, then list the accepted ones in images.json.")


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("fetch", "apply"):
        sys.stderr.write(__doc__ + "\n")
        return 2
    if argv[1] == "fetch":
        fetch()
    else:
        print("\n".join(apply()) or "no curated images; every place keeps imageUrl null")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
