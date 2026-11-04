"""Phrase breaks for the reader: where a line should end so a child can read one natural phrase at a time.

`phrase_ends` adds a boolean `phraseEnd` to each word of a timing document. `True` means "start a new line after this word".
The rule is the same one the browser applies (web/src/phrases.js, which always works the lines out itself and ignores stored flags), so the flags
and the screen agree:

  * a word ending in , ; : or a dash (also followed by closing quotes) ends a phrase when the line already has at least 3 words;
  * a sentence end (the sentence number changes, or the word ends with . ! ?) always ends a phrase;
  * a clause longer than 10 words is split into balanced lines (not "ten words and one"), each cut before a phrase-starting word (to, from, and,
    that ...) when one is near the middle, and never leaving a part shorter than 3 words; words glued by a dash (`join`) are never separated.

Input words are never changed; new dicts are returned.
"""
from __future__ import annotations

import math
import re
from typing import Any, Iterable, Mapping

MIN_WORDS = 3  # a comma only breaks a line that already has this many words
MAX_WORDS = 10  # a clause longer than this is split into balanced lines
MIN_PART = 3  # a split never leaves a part shorter than this
_CLOSERS = "\"')\u201d\u2019"
_SOFT_END = re.compile(rf"[,;:\u2014\u2013][{re.escape(_CLOSERS)}]*$")
_HARD_END = re.compile(rf"[.!?][{re.escape(_CLOSERS)}]*$")
_NOT_LETTER = re.compile(r"[^\W\d_]+", re.UNICODE)

STARTS_PHRASE = frozenset(
    "to in on at by for from of with into onto over under after before during through and but or so that which who when while because if as than until "
    "a al con de del en para por y o pero que cuando mientras porque si como".split()
)


def _key(word: Mapping[str, Any]) -> str:
    return "".join(_NOT_LETTER.findall(str(word.get("text") or "").lower()))


def _balanced_cuts(clause: list[Mapping[str, Any]]) -> list[int]:
    n = len(clause)
    parts = math.ceil(n / MAX_WORDS)
    cuts: list[int] = []
    start = 0
    for k in range(1, parts):
        ideal = round_half_up(n * k / parts)
        lo = max(start + MIN_PART, ideal - 2)
        hi = min(n - MIN_PART * (parts - k), ideal + 2)
        best = -1
        for c in range(lo, hi + 1):
            if c >= n or clause[c].get("join") is True:
                continue  # never cut inside a dash-joined word
            starts = _key(clause[c]) in STARTS_PHRASE
            if best == -1:
                best = c
                continue
            best_starts = _key(clause[best]) in STARTS_PHRASE
            if (starts and not best_starts) or (starts == best_starts and abs(c - ideal) < abs(best - ideal)):
                best = c
        cut = best if best != -1 else min(max(ideal, start + 1), n - 1)
        cuts.append(cut)
        start = cut
    return cuts


def round_half_up(value: float) -> int:
    """JavaScript's Math.round (halves go up), so the browser and these flags cut at the same place."""
    return math.floor(value + 0.5)


def _split_long(clause: list[Mapping[str, Any]]) -> list[list[Mapping[str, Any]]]:
    if len(clause) <= MAX_WORDS:
        return [clause]
    edges = [0, *_balanced_cuts(clause), len(clause)]
    return [clause[edges[i]:edges[i + 1]] for i in range(len(edges) - 1)]


def phrase_ends(words: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return a new list of word dicts, each with a `phraseEnd` bool. The input is left untouched."""
    items = list(words)
    clauses: list[list[Mapping[str, Any]]] = []
    current: list[Mapping[str, Any]] = []
    for index, word in enumerate(items):
        current.append(word)
        following = items[index + 1] if index + 1 < len(items) else None
        text = str(word.get("text") or "")
        ends_sentence = following is None or following.get("sentence") != word.get("sentence") or bool(_HARD_END.search(text))
        ends_phrase = bool(_SOFT_END.search(text)) and len(current) >= MIN_WORDS
        glued = following is not None and following.get("join") is True and not ends_sentence
        if ends_sentence or (ends_phrase and not glued):
            clauses.append(current)
            current = []
    last_of_line = {id(line[-1]) for clause in clauses for line in _split_long(clause)}
    return [{**word, "phraseEnd": id(word) in last_of_line} for word in items]
