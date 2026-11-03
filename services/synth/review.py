"""Pronunciation review: words an independent speech-recognition pass heard as something clearly different.

These are CANDIDATES, not confirmed mistakes. The recognizer's language model can silently "correct" a mispronounced
word, and a rare word can be misheard even when spoken well. Spelling variants (honour/honor) and numerals are
filtered out so the list a content editor sees is short.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Sequence

from asr_words import Heard, is_number, norm

SIMILAR = 0.82  # spelling variants and inflections ("honours"/"honors", "tours"/"tour") score above this
MIN_LENGTH = 3
_EDGE_PUNCTUATION = re.compile(r"^\W+|\W+$")


def _clean(text: str) -> str:
    return _EDGE_PUNCTUATION.sub("", text)


def find_suspects(expected: Sequence[str], heard: Sequence[Heard]) -> list[dict[str, str]]:
    shown = [w for w in expected if norm(w) and not is_number(w)]
    spoken = [h for h in heard if norm(h.text) and not is_number(h.text)]
    matcher = SequenceMatcher(a=[norm(w) for w in shown], b=[norm(h.text) for h in spoken], autojunk=False)

    suspects: list[dict[str, str]] = []
    seen: set[str] = set()
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag != "replace":
            continue
        for k in range(min(a1 - a0, b1 - b0)):
            word, heard_word = shown[a0 + k], spoken[b0 + k].text
            key = norm(word)
            if len(key) < MIN_LENGTH or key in seen:
                continue
            if SequenceMatcher(None, key, norm(heard_word)).ratio() >= SIMILAR:
                continue
            seen.add(key)
            suspects.append({"expected": _clean(word), "heard": _clean(heard_word)})
    return suspects
