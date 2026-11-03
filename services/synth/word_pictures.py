"""Pictures for everyday words: any concrete noun (cookies, tea, trees, a dog) can show a small picture on its word card.

The pictures are OpenMoji icons (CC BY-SA 4.0, https://openmoji.org) bundled with the generator (services/synth/emoji/), so this needs NO network:
it works for every uploaded passage, offline, at no cost per view. `scripts/build_emoji_words.py` builds the word list and the icon folder.
Only nouns get a picture (spaCy decides; a verb or an adjective never does), named people and places are not nouns here, and a word with no
matching icon simply has no picture.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from place_media import image_ext, image_size, target_name, NAME_PATTERN  # noqa: F401  (NAME_PATTERN re-exported for callers and tests)

LOG = logging.getLogger(__name__)
EMOJI_DIR = Path(__file__).with_name("emoji")
TABLE_FILE = Path(__file__).with_name("emoji_words.json")
MAX_WORD_PICTURES = 24
CREDIT = "Picture: OpenMoji, CC BY-SA 4.0"


@lru_cache(maxsize=1)
def load_table() -> dict[str, dict[str, str]]:
    return json.loads(TABLE_FILE.read_text(encoding="utf-8"))["words"]


def _singulars(word: str) -> list[str]:
    """The word itself and its likely singular forms, because a lemmatiser is not always right ("cookies" -> "cooky")."""
    forms = [word]
    if word.endswith("ies") and len(word) > 4:
        forms += [word[:-3] + "y", word[:-1]]
    if word.endswith("es") and len(word) > 3:
        forms.append(word[:-2])
    if word.endswith("s") and len(word) > 3:
        forms.append(word[:-1])
    return forms


def spacy_nouns(text: str, nlp: Any = None) -> list[tuple[str, str]]:
    """(word as written, lemma) for every common noun in the text. Proper nouns (names, places) are excluded."""
    if nlp is None:
        from nlp_shared import shared_nlp

        nlp = shared_nlp()
    return [(t.text.lower(), t.lemma_.lower()) for t in nlp(text) if t.pos_ == "NOUN"]


def word_picture_cards(
    passage_id: str, text: str, nouns: Callable[[str], list[tuple[str, str]]] = spacy_nouns, table: Optional[Mapping[str, Mapping[str, str]]] = None,
    emoji_dir: Path = EMOJI_DIR, existing: Optional[Mapping[str, Mapping[str, Any]]] = None, limit: int = MAX_WORD_PICTURES,
) -> tuple[dict[str, dict[str, Any]], dict[str, bytes]]:
    """Cards (word -> card) and picture files (name -> bytes) for the nouns of `text` that have an icon.

    A card for a word that already has a reviewed card keeps its definition and translations and only gains the picture. Never raises:
    a missing or corrupt icon just means that word has no picture."""
    words = load_table() if table is None else table
    cards: dict[str, dict[str, Any]] = {}
    images: dict[str, bytes] = {}
    try:
        found = nouns(text)
    except Exception as err:  # noqa: BLE001 (a broken language model must never stop publishing)
        LOG.warning("word pictures skipped: %s", err)
        return {}, {}
    for surface, lemma in found:
        key = re.sub(r"[^a-z']", "", surface.lower()).strip("'")
        entry = next((words[c] for c in (lemma, *_singulars(key)) if c in words), None)
        if len(key) < 3 or key in cards or not entry:
            continue
        if len(cards) >= limit:
            break
        try:
            data = (emoji_dir / f"{entry['hex']}.png").read_bytes()
        except OSError:
            continue
        if image_ext(data) != "png":
            continue
        name = target_name(passage_id, key, data, kind="word")
        images[name] = data
        width, height = image_size(data) or (None, None)
        base = dict(existing[key]) if existing and key in existing else {
            "word": key, "syllables": None, "ipa": None, "partOfSpeech": "noun", "definition": "", "example": None, "spanish": []}
        cards[key] = {**base, "imageUrl": f"/data/{name}", "imageAlt": entry["name"], "imageCredit": CREDIT, "imageWidth": width, "imageHeight": height}
    return cards, images
