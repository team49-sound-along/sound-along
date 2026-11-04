"""SSML for Polly: the sentence with <lang> tags around its foreign spans, and the mapping of speech marks back to our words.

Polly speech marks for SSML input carry offsets into the SSML string (UTF-8 bytes, tags included). ``SsmlDoc.origin_of`` turns
such an offset back into an offset in the plain sentence, or None when it points into markup we inserted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from mixed import ForeignSpan

LANG_TAG = {"es": "es-US", "en": "en-US"}  # verified with Polly: <lang xml:lang="es-US"> works on neural, generative and standard
_XML_BAD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;"}


def escape_xml(text: str) -> str:
    cleaned = _XML_BAD.sub(" ", text)
    return "".join(_ENTITIES.get(ch, ch) for ch in cleaned)


@dataclass(frozen=True)
class SsmlDoc:
    ssml: str
    # (ssml_start, ssml_end, plain_start) in characters, one per run of text copied from the sentence; the gaps between runs are markup.
    runs: tuple[tuple[int, int, int], ...]

    def origin_of(self, ssml_char_offset: int) -> int | None:
        for s_start, s_end, plain_start in self.runs:
            if s_start <= ssml_char_offset < s_end:
                return plain_start + _plain_len(self.ssml[s_start:ssml_char_offset])
        return None


def _plain_len(escaped: str) -> int:
    """Characters of plain text that an escaped fragment stands for."""
    return len(re.sub(r"&(?:amp|lt|gt|quot|apos);", "x", escaped))


def build_ssml(text: str, spans: Sequence[ForeignSpan]) -> SsmlDoc:
    """``<speak>`` document for ``text``; spans must be sorted and non-overlapping (mixed.clean_spans)."""
    out = ["<speak>"]
    runs: list[tuple[int, int, int]] = []
    length = len(out[0])
    cursor = 0

    def add_text(start: int, end: int) -> None:
        nonlocal length
        if end <= start:
            return
        piece = escape_xml(text[start:end])
        runs.append((length, length + len(piece), start))
        out.append(piece)
        length += len(piece)

    def add_markup(markup: str) -> None:
        nonlocal length
        out.append(markup)
        length += len(markup)

    for span in spans:
        add_text(cursor, span.start)
        add_markup(f'<lang xml:lang="{LANG_TAG[span.lang]}">')
        add_text(span.start, span.end)
        add_markup("</lang>")
        cursor = span.end
    add_text(cursor, len(text))
    add_markup("</speak>")
    return SsmlDoc("".join(out), tuple(runs))


def word_marks(marks: Sequence[dict[str, Any]], doc: SsmlDoc | None) -> list[dict[str, Any]]:
    """The word marks that belong to the sentence's own words, in order.

    Without tags (doc is None) every word mark counts. With tags a mark whose start lies inside inserted markup is dropped; the
    offset is read as UTF-8 bytes first and, when the text there is not the marked word, as characters (a check, never a guess)."""
    words = [m for m in marks if m.get("type") == "word"]
    if doc is None:
        return words
    raw = doc.ssml.encode("utf-8")
    kept: list[dict[str, Any]] = []
    for mark in words:
        start = mark.get("start")
        if not isinstance(start, int):
            kept.append(mark)
            continue
        value = str(mark.get("value", ""))
        char_offset = len(raw[:start].decode("utf-8", errors="ignore"))
        if not doc.ssml.startswith(value, char_offset) and doc.ssml.startswith(value, start):
            char_offset = start
        if doc.origin_of(char_offset) is not None or not doc.ssml.startswith(value, char_offset):
            kept.append(mark)  # inside our text, or an offset we cannot verify: keep the mark rather than lose a word time
    return kept
