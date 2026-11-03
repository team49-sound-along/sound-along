"""Pronunciation overrides, editable by ReadWorks' content team without phoneme knowledge.

``pronunciations.json`` maps a word to a plain-English respelling ("gaieties": "gay uh teez"). The engine turns
each respelling into phonemes with its own grapheme-to-phoneme step and speaks those phonemes when the word
appears, while the passage still displays and highlights the original spelling.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Mapping

DEFAULT_FILE = Path(__file__).with_name("pronunciations.json")


def load_respellings(path: Path = DEFAULT_FILE) -> dict[str, str]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {word.lower(): respelling for word, respelling in raw.items() if not word.startswith("_")}


def soften_stress(phonemes: str) -> str:
    """Keep the first primary stress and demote later ones to secondary, so syllable-by-syllable respellings
    do not sound like every syllable is stressed."""
    first = phonemes.find("\u02c8")
    if first == -1:
        return phonemes
    return phonemes[: first + 1] + phonemes[first + 1 :].replace("\u02c8", "\u02cc")


def build_phonemes(respellings: Mapping[str, str], to_phonemes: Callable[[str], str]) -> dict[str, str]:
    """Word -> phoneme string. A value written as "/phonemes/" is used verbatim; anything else is a respelling
    converted by the engine. Respellings the engine cannot convert are skipped."""
    phonemes: dict[str, str] = {}
    for word, value in respellings.items():
        if len(value) > 2 and value.startswith("/") and value.endswith("/"):
            phonemes[word] = value[1:-1]
            continue
        converted = soften_stress(to_phonemes(value).replace(" ", "").strip())
        if converted:
            phonemes[word] = converted
    return phonemes


def apply_overrides(sentence: str, phonemes: Mapping[str, str]) -> str:
    """Wrap each overridden word in Kokoro's inline phoneme markup: ``[word](/phonemes/)``."""
    if not phonemes:
        return sentence
    pattern = re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(phonemes, key=len, reverse=True)) + r")\b", re.IGNORECASE)
    return pattern.sub(lambda m: f"[{m.group(1)}](/{phonemes[m.group(1).lower()]}/)", sentence)
