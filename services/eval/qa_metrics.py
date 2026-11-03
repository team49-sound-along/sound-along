"""Pure metrics for the audio quality lab (no model imports, fully unit-tested).

Two independent systems are compared: our timing/text versus an ASR transcript with word timestamps.
Agreement is NOT ground truth (ASR timestamps have their own error); it is a cheap, repeatable regression check
that flags mispronounced or skipped words and timing drift.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "synth"))

from asr_words import Heard, is_number as _is_number, norm  # noqa: E402,F401  (shared with the generator image)



@dataclass(frozen=True)
class Expected:
    i: int
    text: str
    start_ms: int


@dataclass(frozen=True)
class Report:
    words_checked: int
    wer: float
    substitutions: tuple[tuple[str, str], ...]  # (expected, heard): pronunciation suspects
    deletions: tuple[str, ...]  # expected but not heard
    insertions: int
    skipped_numeric: int
    timing_pairs: int
    median_error_ms: float | None
    p95_error_ms: float | None
    within_100ms: float | None
    within_250ms: float | None
    errors_ms: tuple[float, ...] = ()  # every matched word's |timing difference|, for pooling across passages


def percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def compare(expected: Sequence[Expected], heard: Sequence[Heard]) -> Report:
    """Align expected words to heard words (ignoring punctuation, case and numerals) and score them."""
    checkable = [e for e in expected if norm(e.text) and not _is_number(e.text)]
    skipped_numeric = sum(1 for e in expected if _is_number(e.text))
    heard_words = [h for h in heard if norm(h.text) and not _is_number(h.text)]

    matcher = SequenceMatcher(a=[norm(e.text) for e in checkable], b=[norm(h.text) for h in heard_words], autojunk=False)
    subs: list[tuple[str, str]] = []
    dels: list[str] = []
    inserts = 0
    errors_ms: list[float] = []

    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag == "equal":
            for e, h in zip(checkable[a0:a1], heard_words[b0:b1]):
                errors_ms.append(abs(h.start_s * 1000 - e.start_ms))
        elif tag == "replace":
            pairs = min(a1 - a0, b1 - b0)
            subs.extend((checkable[a0 + k].text, heard_words[b0 + k].text) for k in range(pairs))
            dels.extend(e.text for e in checkable[a0 + pairs:a1])
            inserts += (b1 - b0) - pairs
        elif tag == "delete":
            dels.extend(e.text for e in checkable[a0:a1])
        elif tag == "insert":
            inserts += b1 - b0

    n = len(checkable)
    errors = len(subs) + len(dels) + inserts
    share = lambda limit: (sum(1 for x in errors_ms if x <= limit) / len(errors_ms)) if errors_ms else None  # noqa: E731
    return Report(
        words_checked=n,
        wer=(errors / n) if n else 0.0,
        substitutions=tuple(subs),
        deletions=tuple(dels),
        insertions=inserts,
        skipped_numeric=skipped_numeric,
        timing_pairs=len(errors_ms),
        median_error_ms=percentile(errors_ms, 0.5),
        p95_error_ms=percentile(errors_ms, 0.95),
        within_100ms=share(100),
        within_250ms=share(250),
        errors_ms=tuple(errors_ms),
    )
