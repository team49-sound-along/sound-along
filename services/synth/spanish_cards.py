"""Word cards for an uploaded Spanish passage: the English meaning of its harder words ("In English: elephant").

There is no free Spanish dictionary with Spanish definitions that we have checked, so these cards carry a machine translation of the single word
(the same es to en model that translates whole passages), marked machineTranslated. Which words: not names (capitalised inside a sentence), not among
the most common words (spanish_common.json), at least five letters, and only words whose translation differs from the word itself.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Optional

from word_definitions import card_budget

LOG = logging.getLogger(__name__)
COMMON_FILE = Path(__file__).with_name("spanish_common.json")
WORD = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:['’-][A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)*")
MIN_LETTERS = 5


@lru_cache(maxsize=1)
def _common() -> frozenset[str]:
    return frozenset(json.loads(COMMON_FILE.read_text(encoding="utf-8"))["common"])


def _candidates(text: str, common: Any) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for m in WORD.finditer(text):
        word = m.group(0)
        key = word.lower()
        before = text[: m.start()].rstrip()
        starts_sentence = not before or before[-1] in ".!?¿¡:\"“”«»—\n"
        if len(key) < MIN_LETTERS or key in seen or key in common or (word[0].isupper() and not starts_sentence):
            continue
        if word[0].isupper() and starts_sentence and key in common:
            continue
        seen.add(key)
        found.append(key)
    return found


def _plain(word: str) -> str:
    return re.sub(r"[.!?,;:]+$", "", word.strip()).lower()


def spanish_cards(text: str, translate: Callable[[list[str]], list[str]], common: Optional[Any] = None, per_hundred: int = 8, minimum: int = 8, maximum: int = 150) -> dict[str, dict[str, Any]]:
    """word -> card with `translation: {lang: "en", words: [...]}`. Never raises: a missing model or word list just means no cards."""
    try:
        common_words = _common() if common is None else frozenset(common)
        words = _candidates(text, common_words)
        budget = card_budget(len(text.split()), per_hundred, minimum, maximum)
        words = words[: budget * 2]  # a few extra: some will translate to themselves and be dropped
        if not words:
            return {}
        got = translate(words)
        if len(got) != len(words):
            return {}
        cards: dict[str, dict[str, Any]] = {}
        for word, english in zip(words, got):
            en = _plain(english)
            if not en or en == word or len(cards) >= budget:
                continue
            cards[word] = {"word": word, "syllables": None, "ipa": None, "partOfSpeech": None, "definition": "", "example": None, "spanish": [],
                           "translation": {"lang": "en", "words": [en]}, "machineTranslated": True}
        return cards
    except Exception as err:  # noqa: BLE001 (publishing the audio matters more than the cards)
        LOG.warning("Spanish cards skipped: %s", err)
        return {}
