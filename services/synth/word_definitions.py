"""Definition cards for the harder words of an uploaded passage, from a small offline dictionary.

The dictionary is Open English WordNet (CC BY 4.0), trimmed by `scripts/build_word_definitions.py` into `word_definitions.json.gz`:
lemma -> part of speech -> up to three senses [definition, example, pronunciation]. No network is used, so this works for every upload at no cost per view.
Which words get a card: nouns, verbs, adjectives and adverbs (never names) that are not among the most common words of the language, so the
reader sees help on words a child may not know. The number of cards follows the length of the passage (card_budget).
"""
from __future__ import annotations

import gzip
import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

LOG = logging.getLogger(__name__)
TABLE_FILE = Path(__file__).with_name("word_definitions.json.gz")
POS_NAME = {"n": "noun", "v": "verb", "a": "adjective", "r": "adverb"}
SPACY_POS = {"NOUN": "n", "VERB": "v", "ADJ": "a", "ADV": "r"}
PER_HUNDRED, MINIMUM, MAXIMUM = 8, 8, 150
MIN_LETTERS = 4
GLOSS_MAX = 140


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, dict[str, list[str]]], frozenset[str]]:
    with gzip.open(TABLE_FILE, "rt", encoding="utf-8") as f:
        doc = json.load(f)
    return doc["words"], frozenset(doc["common"])


def short_gloss(text: str, limit: int = GLOSS_MAX) -> str:
    """The first clause of a dictionary definition, cut at a word if it is still long."""
    first = re.split(r";\s", text.strip(), maxsplit=1)[0].strip()
    if len(first) <= limit:
        return first
    return first[: limit - 1].rsplit(" ", 1)[0].rstrip(",:- ") + "…"


def card_budget(words: int, per_hundred: int = PER_HUNDRED, minimum: int = MINIMUM, maximum: int = MAXIMUM) -> int:
    return max(minimum, min(maximum, words * per_hundred // 100))


STOP = frozenset("the a an and or of to in on at is are was were be been it its this that with for as by from not but they them their he she his her we you i".split())


def _context(found: list[tuple[str, str, str]]) -> frozenset[str]:
    return frozenset(w for surface, lemma, _ in found for w in (surface, lemma) if w not in STOP and len(w) > 2)


def pick_sense(senses: list[list[str]], context: frozenset[str]) -> list[str]:
    """The sense whose definition and example share most words with the passage; the earlier (more frequent) sense wins a tie. A small bias keeps
    a rare sense from beating the common one on one chance word."""
    def score(item: tuple[int, list[str]]) -> tuple[float, int]:
        n, sense = item
        overlap = len(context & {w for w in re.findall(r"[a-z]+", (sense[0] + " " + (sense[1] if len(sense) > 1 else "")).lower()) if w not in STOP and len(w) > 2})
        return (overlap - 0.5 * n, -n)
    return max(enumerate(senses), key=score)[1]


def spacy_tokens(text: str, nlp: Any = None) -> list[tuple[str, str, str]]:
    """(word as written, lemma, spaCy part of speech) for every token. Names are PROPN and are skipped by the caller."""
    if nlp is None:
        from nlp_shared import shared_nlp

        nlp = shared_nlp()
    return [(t.text.lower(), t.lemma_.lower(), t.pos_) for t in nlp(text)]


def definition_cards(
    text: str, table: Optional[Mapping[str, Mapping[str, list[str]]]] = None, common: Optional[Any] = None,
    tokens: Callable[[str], list[tuple[str, str, str]]] = spacy_tokens, existing: Optional[Mapping[str, Mapping[str, Any]]] = None,
    per_hundred: int = PER_HUNDRED, minimum: int = MINIMUM, maximum: int = MAXIMUM,
) -> dict[str, dict[str, Any]]:
    """word (as written, lower case) -> card for the harder words of `text`. A reviewed card in `existing` keeps its text and only gains what it
    lacks. Never raises: a broken dictionary or language model just means no definition cards."""
    try:
        words, common_words = _load() if table is None else (table, frozenset(common or ()))
        found = tokens(text)
    except Exception as err:  # noqa: BLE001 (a missing data file must never stop publishing)
        LOG.warning("definition cards skipped: %s", err)
        return {}
    budget = card_budget(len(found), per_hundred, minimum, maximum)
    context = _context(found)
    cards: dict[str, dict[str, Any]] = {}
    for surface, lemma, pos in found:
        key = re.sub(r"[^a-z']", "", surface).strip("'")
        letter = SPACY_POS.get(pos)
        if not letter or len(key) < MIN_LETTERS or key in cards or lemma in common_words or key in common_words:
            continue
        senses = (words.get(lemma) or words.get(key) or {}).get(letter)
        if not senses or not senses[0] or not senses[0][0]:
            continue
        sense = pick_sense(senses, context)
        if len(cards) >= budget and key not in (existing or {}):
            continue
        gloss, example, ipa = (list(sense) + ["", ""])[:3]
        base = dict(existing[key]) if existing and key in existing else {"word": key, "syllables": None, "ipa": None, "partOfSpeech": POS_NAME[letter], "definition": "", "example": None, "spanish": []}
        cards[key] = {**base, "word": base.get("word") or key, "ipa": base.get("ipa") or ipa or None, "partOfSpeech": base.get("partOfSpeech") or POS_NAME[letter],
                      "definition": base.get("definition") or short_gloss(gloss), "example": base.get("example") or example or None}
    return cards
