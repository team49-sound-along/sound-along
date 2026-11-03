"""Build the word -> picture list for word cards from OpenMoji (CC BY-SA 4.0, https://openmoji.org). One-off, needs network; the OUTPUT is committed.

  .venv/bin/python scripts/build_emoji_words.py

Writes services/synth/emoji_words.json ({word: {hex, name}}) and the 72x72 colour PNG of every emoji it uses into services/synth/emoji/, so the
generator needs no network at all to give a word a picture. Only concrete things are kept (food, animals, plants, objects, places, weather);
people, flags, symbols, faces and clock times are left out, and so are very generic words that would give a misleading picture.
Standard library only.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

VERSION = "15.0.0"
BASE = f"https://cdn.jsdelivr.net/gh/hfg-gmuend/openmoji@{VERSION}"
OUT = Path(__file__).resolve().parent.parent / "services" / "synth"
GROUPS = {"food-drink", "animals-nature", "objects", "travel-places", "activities"}
SKIP_SUBGROUPS = {"time", "person-role", "family", "transport-air"}  # clocks make "time" mean a clock; people are not word pictures
STOP = {"place", "time", "day", "way", "thing", "part", "side", "life", "world", "head", "mark", "kind", "case", "point", "note", "light", "case",
        "fine", "game", "play", "mail", "wave", "star", "top", "back", "end", "set", "run", "face", "business", "office", "stop", "sign", "square",
        "cross", "match", "plant", "address", "article", "bill", "board", "cell", "chain", "check", "club", "cut", "dress"}


def fetch(url: str) -> bytes:
    time.sleep(0.15)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "SoundAlongCards/1.0 (https://github.com/rohanreigns007/sound-along; one-off build)"}), timeout=30) as res:  # noqa: S310
        return res.read()


# Words whose obvious picture is not what OpenMoji's own name or tags would pick (checked by hand).
OVERRIDES = {"car": "1F697", "cars": "1F697", "money": "1F4B0", "water": "1F4A7", "fire": "1F525", "sun": "2600", "moon": "1F319", "rain": "1F327",
             "book": "1F4D6", "books": "1F4D6", "tea": "1F375", "cup": "1F375", "bread": "1F35E", "milk": "1F95B", "apple": "1F34E", "egg": "1F95A",
             "tree": "1F333", "trees": "1F333", "flower": "1F338", "flowers": "1F338", "bus": "1F68C", "train": "1F686", "boat": "26F5", "bike": "1F6B2",
             "bicycle": "1F6B2", "airplane": "2708", "plane": "2708", "snow": "2744", "cloud": "2601", "mountain": "26F0", "mountains": "26F0",
             "school": "1F3EB", "hospital": "1F3E5", "castle": "1F3F0", "bridge": "1F309", "city": "1F3D9", "cities": "1F3D9", "beach": "1F3D6",
             "key": "1F511", "bell": "1F514", "clock": "1F570", "phone": "1F4F1", "computer": "1F4BB", "camera": "1F4F7", "ball": "26BD", "kite": "1FA81"}
# Too generic or abstract: any picture would mislead.
NO_PICTURE = {"peace", "fortune", "chests", "chest", "glass", "eye", "search", "view", "views", "opening", "fields", "field", "woman", "credit",
              "evening", "morning", "animals", "animal", "pounds", "pound", "paper", "ground", "park", "parks"}  # "park" would show a NATIONAL park
LOOSE_TAG_SUBGROUPS = ("food-", "drink", "dishware", "animal-", "plant-")


def main() -> int:
    data = json.loads(fetch(f"{BASE}/data/openmoji.json"))
    keep = [e for e in data if e["group"] in GROUPS and e["subgroups"] not in SKIP_SUBGROUPS and not e.get("skintone") and "-" not in e["hexcode"]]
    ordered = sorted(keep, key=lambda x: x["order"])
    words: dict[str, dict[str, str]] = {}

    def add(word: str, e: dict) -> None:
        word = word.lower().strip()
        if re.fullmatch(r"[a-z]{3,}", word) and word not in STOP and word not in NO_PICTURE and word not in words:
            words[word] = {"hex": e["hexcode"], "name": e["annotation"]}

    by_hex = {e["hexcode"]: e for e in data}
    for word, hexcode in OVERRIDES.items():
        if hexcode in by_hex:
            words[word] = {"hex": hexcode, "name": by_hex[hexcode]["annotation"]}
    for e in ordered:  # 1. the emoji's own one-word name ("cookie")
        if " " not in e["annotation"]:
            add(e["annotation"], e)
    for e in ordered:  # 2. the head noun of its name ("deciduous tree" -> tree, "water buffalo" -> buffalo)
        add(e["annotation"].split()[-1], e)
    for e in ordered:  # 3. loose tags, only where they are reliable: food, drinks, animals, plants
        if e["subgroups"].startswith(LOOSE_TAG_SUBGROUPS):
            for tag in e["tags"].split(","):
                add(tag, e)
    needed = sorted({w["hex"] for w in words.values()})
    folder = OUT / "emoji"
    folder.mkdir(exist_ok=True)
    for old in folder.glob("*.png"):
        if old.stem not in needed:
            old.unlink()
    for hexcode in needed:
        target = folder / f"{hexcode}.png"
        if not target.exists():
            target.write_bytes(fetch(f"{BASE}/color/72x72/{hexcode}.png"))
    (OUT / "emoji_words.json").write_text(json.dumps({"openmoji": VERSION, "license": "CC BY-SA 4.0", "words": dict(sorted(words.items()))}, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(words)} words -> {len(needed)} pictures ({sum(p.stat().st_size for p in folder.glob('*.png')) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
