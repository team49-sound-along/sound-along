"""Add word pictures to the demo texts' cards: reviewed cards keep their definitions and only gain a picture, other everyday nouns get picture cards.

  .venv/bin/python scripts/apply_word_pictures.py

Offline. Uses the same finder the live publish step uses (services/synth/word_pictures.py), so the demo texts and uploaded passages behave alike.
Writes samples/cards/<id>.cards.json and the icons into samples/cards/images/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "services" / "synth"), str(ROOT / "services" / "parse")]
from tokenizer import tokenize_html  # noqa: E402
from word_pictures import word_picture_cards  # noqa: E402

CARDS = ROOT / "samples" / "cards"
SAMPLES = ROOT / "samples"


def main() -> int:
    images_dir = CARDS / "images"
    images_dir.mkdir(exist_ok=True)
    for path in sorted(CARDS.glob("*.cards.json")):
        passage_id = path.name.removesuffix(".cards.json")
        passage = json.loads((SAMPLES / f"{passage_id}.json").read_text(encoding="utf-8"))
        text = " ".join(t.text for t in tokenize_html(passage["content"]))
        document = json.loads(path.read_text(encoding="utf-8"))
        words = {k: {f: v for f, v in c.items() if not f.startswith("image")} for k, c in document["words"].items()}  # start without pictures: idempotent
        new_cards, images = word_picture_cards(passage_id, text, existing=words, limit=60)
        for stale in images_dir.glob(f"{passage_id}.word-*"):
            stale.unlink()
        for name, data in images.items():
            (images_dir / name).write_bytes(data)
        document["words"] = {**words, **new_cards}
        path.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{passage_id[:8]}: {len(new_cards)} word pictures ({', '.join(new_cards)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
