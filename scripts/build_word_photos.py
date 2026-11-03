"""Build the word -> real photo list for word cards from Wikipedia / Wikimedia Commons. One-off, needs network; the OUTPUT is committed.

  .venv/bin/python scripts/build_word_photos.py            # fetch candidates into scripts/_word_photos_work/ (git-ignored) and write a review sheet
  .venv/bin/python scripts/build_word_photos.py --publish  # copy the approved photos into services/synth/word_photos/ and write word_photos.json

A word gets a photo only when its Wikipedia article (not a disambiguation page) has a JPEG lead picture under a free licence (CC0, public
domain, CC BY, CC BY-SA). Authors and licences are recorded and shown on the word card. Words with no such photo simply have no picture.
The candidate words are the concrete nouns of the old icon table: an icon's own one-word name, its head noun, and the hand-checked overrides.
Standard library only (the review sheet needs Pillow when it is installed).
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "services" / "synth"), str(Path(__file__).resolve().parent)]
from place_media import USER_AGENT, clean_artist, credit_line, image_ext, license_ok  # noqa: E402

WORK = Path(__file__).resolve().parent / "_word_photos_work"
OUT = ROOT / "services" / "synth"
API = "https://en.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
THUMB = 330  # a standard Wikimedia thumbnail step
MAX_BYTES = 70_000
PACE = 1.5
# Hand-chosen article titles where the plain word is ambiguous or points at the wrong thing (checked by reading the review sheet).
TITLES = {"cookie": "Cookie", "cookies": "Cookie", "tea": "Tea", "cup": "Cup", "bus": "Bus", "plane": "Airplane", "airplane": "Airplane", "bike": "Bicycle",
          "bicycle": "Bicycle", "ball": "Ball", "boat": "Boat", "fire": "Fire", "water": "Water", "money": "Money", "book": "Book", "books": "Book",
          "city": "City", "cities": "City", "tree": "Tree", "trees": "Tree", "flower": "Flower", "flowers": "Flower", "ship": "Ship", "ships": "Ship",
          "house": "House", "car": "Car", "cars": "Car", "key": "Key (lock)", "bell": "Bell", "clock": "Clock", "phone": "Mobile phone", "computer": "Computer",
          "bridge": "Bridge", "castle": "Castle", "school": "School", "hospital": "Hospital", "beach": "Beach", "mountain": "Mountain", "mountains": "Mountain",
          "snow": "Snow", "cloud": "Cloud", "rain": "Rain", "moon": "Moon", "sun": "Sun", "bread": "Bread", "milk": "Milk", "apple": "Apple", "egg": "Egg"}
# Words whose photo would be a person, a diagram or a misleading thing even when the article has a free JPEG (decided from the review sheet).
REJECT = set("""alembic amulet arts ballot banknote bat bikini blowfish bomb briefs cactus cigarette cityscape clover cloud coat coffin construction corn
cream cricket crutch dividers dodo dusk elevator fondue football fountain green handbag handle hat hole hook jar kaaba kimono label lipstick magnet mask
mosque necktie night oden pistol plunger pong pump rain receipt ruler sake scroll shower shrine snow stars stone straw suit sunglasses swimsuit synagogue
syringe tamale temple toilet trackball tray unicorn uniform urn videocassette voltage volume wand wedding wheelchair window wing wings wood yen""".split())  # reviewed by eye on the contact sheets: people, underwear, weapons, alcohol, religious buildings, illustrations/paintings and photos that do not show the word
# Words whose own article has no usable free photo: a specific Commons file chosen by a person (word -> (file, name shown in the alt text)).
EXTRA_FILES = {"cookie": ("Chocolate chip cookies on cutting board.jpg", "cookie"), "apple": ("Red Apple.jpg", "apple"), "egg": ("Huevo frito.jpg", "fried egg")}
GENERIC_FILE = re.compile(r"(map|diagram|logo|flag|coat[_ ]of|symbol|icon|chart|illustration|drawing|painting|sketch|engraving|portrait|statue)", re.I)


def get(url: str, binary: bool = False):
    for attempt in range(5):
        time.sleep(PACE)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=40) as r:  # noqa: S310
                body = r.read()
            return body if binary else json.loads(body)
        except urllib.error.HTTPError as err:
            if err.code == 429 and attempt < 4:
                time.sleep(int(err.headers.get("Retry-After", "20")) + 5 * attempt)
                continue
            raise
    raise RuntimeError("unreachable")


def candidates() -> dict[str, str]:
    """word -> article title, from the old icon table (concrete nouns only)."""
    table = json.loads((OUT / "emoji_words.json").read_text(encoding="utf-8"))["words"]
    words: dict[str, str] = {}
    for word, e in table.items():
        name = e["name"].lower()
        if word == name or word == name.split()[-1] or word in TITLES:
            words[word] = TITLES.get(word, word.capitalize())
    return words


def lead_images(titles: list[str]) -> dict[str, dict]:
    """title as asked -> {article, file, thumb} for non-disambiguation articles that have a lead picture."""
    out: dict[str, dict] = {}
    for i in range(0, len(titles), 40):
        chunk = titles[i:i + 40]
        q = urllib.parse.urlencode({"action": "query", "format": "json", "redirects": 1, "titles": "|".join(chunk), "prop": "pageimages|pageprops",
                                    "piprop": "thumbnail|name", "pithumbsize": THUMB, "ppprop": "disambiguation"})
        data = get(f"{API}?{q}")["query"]
        back = {t: t for t in chunk}
        for key in ("normalized", "redirects"):
            for m in data.get(key, []):
                for k, v in list(back.items()):
                    if v == m["from"]:
                        back[k] = m["to"]
        pages = {p["title"]: p for p in data["pages"].values()}
        for asked, final in back.items():
            p = pages.get(final)
            if p and "disambiguation" not in p.get("pageprops", {}) and p.get("pageimage") and p.get("thumbnail"):
                out[asked] = {"article": final, "file": p["pageimage"], "thumb": p["thumbnail"]["source"]}
    return out


def file_meta(files: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(files), 40):
        chunk = files[i:i + 40]
        q = urllib.parse.urlencode({"action": "query", "format": "json", "titles": "|".join("File:" + f for f in chunk), "prop": "imageinfo",
                                    "iiprop": "extmetadata|mime|size", "iiextmetadatafilter": "LicenseShortName|Artist"})
        for p in get(f"{COMMONS}?{q}")["query"]["pages"].values():
            ii = (p.get("imageinfo") or [{}])[0]
            md = ii.get("extmetadata", {})
            out[p["title"].removeprefix("File:").replace(" ", "_")] = {
                "mime": ii.get("mime"), "w": ii.get("width", 0), "h": ii.get("height", 0),
                "license": md.get("LicenseShortName", {}).get("value"), "artist": md.get("Artist", {}).get("value")}
    return out


def fetch_all() -> None:
    WORK.mkdir(exist_ok=True)
    (WORK / "photos").mkdir(exist_ok=True)
    cand = candidates()
    print(f"{len(cand)} candidate words")
    leads = lead_images(sorted(set(cand.values())))
    meta = file_meta(sorted({v["file"] for v in leads.values()}))
    kept: dict[str, dict] = {}
    for word, title in sorted(cand.items()):
        lead = leads.get(title)
        if not lead or word in REJECT:
            continue
        m = meta.get(lead["file"].replace(" ", "_"), {})
        if m.get("mime") != "image/jpeg" or not license_ok(m.get("license")) or GENERIC_FILE.search(lead["file"]) or m.get("w", 0) < 330:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        target = WORK / "photos" / f"{slug}.jpg"
        if not target.exists():
            try:
                data = get(lead["thumb"], binary=True)
            except Exception as err:  # noqa: BLE001
                print("skip", word, err)
                continue
            if image_ext(data) != "jpg" or len(data) > MAX_BYTES:
                continue
            target.write_bytes(data)
        kept[word] = {"file": target.name, "name": title.split(" (")[0].lower(), "article": lead["article"],
                      "credit": credit_line(clean_artist(m.get("artist")), m["license"], kind="Photo")}
    for word, (fname, name) in EXTRA_FILES.items():
        info = get(f"{COMMONS}?" + urllib.parse.urlencode({"action": "query", "format": "json", "titles": "File:" + fname, "prop": "imageinfo", "iiprop": "extmetadata|mime|url",
                                                           "iiurlwidth": THUMB, "iiextmetadatafilter": "LicenseShortName|Artist"}))
        ii = list(info["query"]["pages"].values())[0]["imageinfo"][0]
        md = ii["extmetadata"]
        data = get(ii["thumburl"], binary=True)
        if ii["mime"] == "image/jpeg" and license_ok(md["LicenseShortName"]["value"]) and image_ext(data) == "jpg" and len(data) <= MAX_BYTES:
            (WORK / "photos" / f"{word}.jpg").write_bytes(data)
            kept[word] = {"file": f"{word}.jpg", "name": name, "article": fname, "credit": credit_line(clean_artist(md.get("Artist", {}).get("value")), md["LicenseShortName"]["value"], kind="Photo")}
    (WORK / "candidates.json").write_text(json.dumps(kept, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(kept)} words have a free photo")
    sheet(kept)


def sheet(kept: dict[str, dict]) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Pillow not installed: no review sheet")
        return
    words = sorted(kept)
    per = 40
    for n in range(0, len(words), per):
        chunk = words[n:n + per]
        cols, cell = 8, 150
        img = Image.new("RGB", (cols * cell, ((len(chunk) + cols - 1) // cols) * (cell + 16)), "white")
        d = ImageDraw.Draw(img)
        for i, w in enumerate(chunk):
            x, y = (i % cols) * cell, (i // cols) * (cell + 16)
            try:
                p = Image.open(WORK / "photos" / kept[w]["file"]).convert("RGB")
                p.thumbnail((cell - 4, cell - 4))
                img.paste(p, (x + 2, y + 2))
            except OSError:
                pass
            d.text((x + 3, y + cell), w[:22], fill="black")
        img.save(WORK / f"sheet-{n // per + 1:02d}.png")
    print(f"review sheets: {WORK}/sheet-*.png")


def publish() -> None:
    kept = json.loads((WORK / "candidates.json").read_text(encoding="utf-8"))
    kept = {w: e for w, e in kept.items() if w not in REJECT}
    folder = OUT / "word_photos"
    folder.mkdir(exist_ok=True)
    for old in folder.glob("*.jpg"):
        old.unlink()
    for e in kept.values():
        (folder / e["file"]).write_bytes((WORK / "photos" / e["file"]).read_bytes())
    doc = {"source": "Wikipedia lead pictures on Wikimedia Commons", "words": {w: {"file": e["file"], "name": e["name"], "credit": e["credit"]} for w, e in sorted(kept.items())}}
    (OUT / "word_photos.json").write_text(json.dumps(doc, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(kept)} words, {len(set(e['file'] for e in kept.values()))} photos ({sum(p.stat().st_size for p in folder.glob('*.jpg')) // 1024} KB)")


if __name__ == "__main__":
    publish() if "--publish" in sys.argv else fetch_all()
