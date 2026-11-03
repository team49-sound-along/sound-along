"""Map an engine's own word tokens onto our display tokens (the "normalization map").

Engines split text differently than we do ("year" + "!", "there" + "'s", numbers spoken as words).
We keep our display tokens as the source of truth and consume engine tokens until the
alphanumeric characters match, so a highlight always lands on the word the student sees.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from asr_words import norm  # noqa: E402  (one accent-tolerant definition shared with the recognizer code)


@dataclass(frozen=True)
class EngineToken:
    text: str
    start_s: Optional[float]
    end_s: Optional[float]


@dataclass(frozen=True)
class MappedWord:
    start_s: float
    end_s: float
    aligned: bool  # False when we had to estimate (mismatch or missing timestamps)


def map_words(display: Sequence[str], engine: Sequence[EngineToken], fallback_start: float = 0.0) -> list[MappedWord]:
    """One MappedWord per display word, in order. Never raises on a mismatch; marks it instead."""
    mapped: list[MappedWord] = []
    k = 0
    cursor = fallback_start
    for word in display:
        target = norm(word)
        if not target:  # punctuation-only display token such as a dash
            mapped.append(MappedWord(cursor, cursor, False))
            continue
        acc = ""
        starts: list[float] = []
        ends: list[float] = []
        while k < len(engine) and len(acc) < len(target):
            token = engine[k]
            k += 1
            acc += norm(token.text)
            if token.start_s is not None:
                starts.append(token.start_s)
            if token.end_s is not None:
                ends.append(token.end_s)
        # Trailing punctuation tokens ("." "!" ",") belong to the word they follow.
        while k < len(engine) and not norm(engine[k].text):
            token = engine[k]
            k += 1
            if token.end_s is not None:
                ends.append(token.end_s)
        ok = acc == target and bool(starts) and bool(ends)
        start = min(starts) if starts else cursor
        end = max(ends) if ends else start
        end = max(end, start)
        mapped.append(MappedWord(start, end, ok))
        cursor = end
    return mapped
