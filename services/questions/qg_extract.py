"""Pull a JSON value out of a model reply that may wrap it in prose, code fences or reasoning text."""
from __future__ import annotations

import json
from typing import Any

_DECODER = json.JSONDecoder()


def _candidates(text: str) -> list[Any]:
    """Every top-level JSON object or array found in the text, in order. Braces inside JSON strings are handled by the decoder."""
    found: list[Any] = []
    position = 0
    while position < len(text):
        if text[position] in "{[":
            try:
                value, end = _DECODER.raw_decode(text, position)
            except json.JSONDecodeError:
                position += 1
                continue
            found.append(value)
            position = end
        else:
            position += 1
    return found


def extract_json(text: str, require_key: str | None = None) -> Any:
    """Return the JSON value in `text`.

    With `require_key`, only objects that contain that key count (a reasoning model may print scratch JSON before its answer).
    Without it, the largest value wins, because the final answer is normally the biggest one. Raises ValueError if nothing fits.
    """
    candidates = _candidates(text)
    if require_key is not None:
        candidates = [c for c in candidates if isinstance(c, dict) and require_key in c]
    if not candidates:
        raise ValueError("no JSON value found in the model reply" + (f" with the key {require_key!r}" if require_key else ""))
    return max(candidates, key=lambda c: len(json.dumps(c)))
