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

CARDS = Path(__file__).resolve().parent.parent / "samples" / "cards"
NAME_PATTERN = re.compile(r"[0-9a-f-]{36}\.place-[a-z0-9-]{1,60}-[0-9a-f]{8}\.(?:jpg|png)")
MAX_ALT = 125  # a screen reader reads alt text in one go; longer belongs in the caption
MAX_BYTES = 400_000
THUMB_WIDTH = 500
PACE_SECONDS = 1.2
USER_AGENT = "SoundAlongCards/1.0 (https://github.com/rohanreigns007/sound-along; one-off content build, no personal data)"
_BLOCKED = re.compile(r"\b(NC|ND)\b|NON.?COMMERCIAL|NO.?DERIV|GFDL|FAIR USE|ALL RIGHTS")
_ALLOWED = re.compile(r"^(CC0( .*)?|CC[ -]BY(-SA)?( \d(\.\d)?)?( .*)?|PUBLIC DOMAIN|PD([ -].*)?)$")


# ---- pure helpers (tested) -------------------------------------------------------------------------------------------------------
def license_ok(name: str | None) -> bool:
    """Only free licences: CC0, public domain, CC BY, CC BY-SA. Non-commercial, no-derivatives, GFDL and unknown are refused."""
    if not name or not name.strip():
        return False
    upper = name.strip().upper()
    return not _BLOCKED.search(upper) and bool(_ALLOWED.match(upper))


def clean_artist(value: str | None) -> str:
    """Plain-text author from Commons' HTML credit: tags removed, entities decoded, whitespace collapsed, capped at 80 characters."""
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", "", value or ""))).strip()
    text = text.replace("<", "").replace(">", "")
    return text[:80].strip() or "Unknown author"


def credit_line(artist: str, license_name: str) -> str:
    kind = "Image" if license_name.strip().upper().startswith(("PUBLIC DOMAIN", "PD", "CC0")) else "Photo"
    return f"{kind}: {artist}, {license_name}, via Wikimedia Commons"


def image_ext(data: bytes) -> str | None:
    """"jpg" or "png" when the BYTES are really that, otherwise None. SVG, HTML and everything else is refused."""
    if len(data) >= 4 and data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return None


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60].strip("-") or "place"


def target_name(passage_id: str, place: str, data: bytes) -> str:
    """<passage id>.place-<slug>-<8 hex of the content hash>.<ext>: the hash makes the file safe to cache for a year."""
    ext = image_ext(data)
    if ext is None:
        raise ValueError("not a JPEG or PNG image")
    return f"{passage_id}.place-{slug(place)}-{hashlib.sha256(data).hexdigest()[:8]}.{ext}"


def alt_problem(alt: object, place: str) -> str | None:
    if not isinstance(alt, str) or not alt.strip():
        return "alt text is required for every picture"
    if len(alt) > MAX_ALT:
        return f"alt text is over {MAX_ALT} characters"
    if "<" in alt or ">" in alt:
        return "alt text must be plain text"
    if alt.strip().lower() == place.strip().lower():
        return "alt text must describe the picture, not repeat the place name"
    return None


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
            "imageCredit": credit_line(clean_artist(entry.get("artist")), entry["license"].strip()),
        }

    images = cards / "images"
    images.mkdir(exist_ok=True)
    for stale in images.iterdir():
        if stale.is_file() and stale.name not in files:
            stale.unlink()
    for name, data in files.items():
        (images / name).write_bytes(data)

    for path in sorted(cards.glob("*.cards.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        passage_id = path.name.removesuffix(".cards.json")
        places = {
            key: {**place, **{"imageUrl": None, "imageAlt": None, "imageCredit": None}, **chosen.get((passage_id, key), {})}
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
    from fetch_place_summaries import PLACES

    cache_file = cards / "places.images.raw.json"
    cache: dict = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    out_dir = cards / "images.candidates"
    out_dir.mkdir(exist_ok=True)
    report = []
    for passage_id, places in PLACES.items():
        for place, title in places.items():
            row = {"passageId": passage_id, "place": place, "title": title}
            try:
                q = _get("https://en.wikipedia.org/w/api.php?action=query&prop=pageimages&piprop=name&format=json&titles=" + urllib.parse.quote(title), cache=cache)
                file_name = next(iter(q["query"]["pages"].values())).get("pageimage")
                if not file_name:
                    report.append({**row, "rejected": "the article has no lead image"})
                    continue
                c = _get("https://commons.wikimedia.org/w/api.php?action=query&prop=imageinfo&format=json&iiprop=url|size|mime|extmetadata"
                         f"&iiurlwidth={THUMB_WIDTH}&iiextmetadatafilter=LicenseShortName|Artist&titles=" + urllib.parse.quote("File:" + file_name), cache=cache)
                info = next(iter(c["query"]["pages"].values()))["imageinfo"][0]
                meta = info.get("extmetadata", {})
                licence = (meta.get("LicenseShortName") or {}).get("value")
                row.update(file=file_name, license=licence, artist=clean_artist((meta.get("Artist") or {}).get("value")), mime=info.get("mime"),
                           original=f"{info.get('width')}x{info.get('height')}", page="https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(file_name.replace(" ", "_")))
                if info.get("mime") not in ("image/jpeg", "image/png"):
                    report.append({**row, "rejected": f"not a raster photo ({info.get('mime')})"})
                    continue
                if not license_ok(licence):
                    report.append({**row, "rejected": f"licence {licence!r} is not allowed"})
                    continue
                data = _get(info["thumburl"], binary=True)
                ext = image_ext(data)
                if ext is None:
                    report.append({**row, "rejected": "downloaded bytes are not a JPEG or PNG"})
                    continue
                candidate = f"{slug(place)}.{ext}"
                (out_dir / candidate).write_bytes(data)
                report.append({**row, "candidate": candidate, "bytes": len(data)})
                print(f"{place:14} {licence:12} {len(data) // 1024:>4} KB  {candidate}")
            except (urllib.error.URLError, ValueError, KeyError, StopIteration, IndexError, TimeoutError) as err:
                report.append({**row, "rejected": f"{type(err).__name__}: {err}"})
                sys.stderr.write(f"  {place}: {err}\n")
            cache_file.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    (cards / "images.candidates.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n{sum(1 for r in report if 'candidate' in r)} candidates, {sum(1 for r in report if 'rejected' in r)} rejected. Open them, then list the accepted ones in images.json.")


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
