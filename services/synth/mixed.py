"""Mixed-language narration: when and how foreign words inside a passage are detected.

An English passage can carry Spanish names ("El Salvador") and a Spanish passage English ones; a single-language voice reads
them with the wrong accent. Detection lives in langspans.py (``detect_spans``); this module decides whether it may run and
makes sure a faulty detector can never break a job.

Switches: env MIXED_LANGUAGE=off turns everything off; the passage setting ``settings.mixedLanguage`` (default true) turns it
off for one passage; env MIXED_LANGUAGE_KOKORO=on additionally lets Kokoro splice foreign segments (default off, Polly only).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

LOG = logging.getLogger(__name__)
_OFF = {"off", "false", "0", "no"}
LANGS = ("en", "es")


@dataclass(frozen=True)
class ForeignSpan:
    """A run of the sentence to speak in another language. Same shape as langspans.Span: [start, end) characters of the plain text."""

    start: int
    end: int
    lang: str


def env_enabled(env: Mapping[str, str] | None = None) -> bool:
    return (env if env is not None else os.environ).get("MIXED_LANGUAGE", "").strip().lower() not in _OFF


def kokoro_enabled(env: Mapping[str, str] | None = None) -> bool:
    return (env if env is not None else os.environ).get("MIXED_LANGUAGE_KOKORO", "").strip().lower() == "on"


def setting_enabled(settings: Mapping[str, Any] | None) -> bool:
    value = (settings or {}).get("mixedLanguage", True)
    return not (value is False or (isinstance(value, str) and value.strip().lower() in _OFF))


def passage_enabled(passage: Mapping[str, Any]) -> bool:
    """True when the passage may have foreign words spoken in their own language."""
    return env_enabled() and setting_enabled(passage.get("settings"))


def fingerprint_marker(passage: Mapping[str, Any]) -> str | None:
    """Goes into the passage fingerprint only while the feature can change the audio, so a switch flipped either way regenerates."""
    if not passage_enabled(passage):
        return None
    return "v1+kokoro" if kokoro_enabled() else "v1"


def clean_spans(text: str, spans: Iterable[Any]) -> list[ForeignSpan]:
    """Valid, sorted, non-overlapping spans inside ``text``; anything malformed (or overlapping an earlier span) is dropped."""
    out: list[ForeignSpan] = []
    for span in sorted(spans, key=lambda s: (getattr(s, "start", 0), getattr(s, "end", 0))):
        start, end, lang = getattr(span, "start", None), getattr(span, "end", None), getattr(span, "lang", None)
        if not (isinstance(start, int) and isinstance(end, int)) or lang not in LANGS:
            continue
        if start < 0 or end > len(text) or end <= start or not text[start:end].strip():
            continue
        if out and start < out[-1].end:
            continue
        out.append(ForeignSpan(start, end, lang))
    return out


def spans_for(text: str, base_lang: str) -> list[ForeignSpan]:
    """Foreign spans of ``text`` (the plain text that will be synthesized). No spans when the detector is missing or fails."""
    if not text.strip() or not env_enabled():
        return []
    try:
        from langspans import detect_spans  # imported lazily: the detector lands separately
    except ImportError:
        return []
    try:
        return clean_spans(text, detect_spans(text, base_lang))
    except Exception:  # noqa: BLE001 (a detector fault must never lose a passage)
        LOG.warning("language detection failed; narrating without foreign spans", exc_info=True)
        return []


def segments(text: str, spans: Sequence[ForeignSpan], base_lang: str) -> list[tuple[str, str]]:
    """``text`` cut into (language, piece) runs in order; the pieces joined give ``text`` back."""
    out: list[tuple[str, str]] = []
    cursor = 0
    for span in spans:
        if span.start > cursor:
            out.append((base_lang, text[cursor:span.start]))
        out.append((span.lang, text[span.start:span.end]))
        cursor = span.end
    if cursor < len(text):
        out.append((base_lang, text[cursor:]))
    return out
