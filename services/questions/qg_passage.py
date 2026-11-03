"""Rebuild a passage's sentences from its timing file. The sentence numbers are the same ones the website uses."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def sentences_from_timing(doc: Mapping[str, Any]) -> list[str]:
    """One string per sentence, indexed by the timing file's `sentence` number (which must run 0, 1, 2 ... without gaps)."""
    words = doc.get("words") or []
    if not words:
        raise ValueError("the timing file has no words")
    grouped: dict[int, list[str]] = {}
    for word in words:
        grouped.setdefault(int(word["sentence"]), []).append(str(word["text"]))
    numbers = list(grouped)
    if numbers != list(range(len(numbers))):
        raise ValueError(f"sentence numbers must run 0..{len(numbers) - 1} without gaps, got {numbers[:6]}")
    return [" ".join(parts) for parts in grouped.values()]
