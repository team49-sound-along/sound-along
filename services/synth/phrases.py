"""Phrase breaks for the reader: where a line should end so a child can read one natural phrase at a time.

`phrase_ends` adds a boolean `phraseEnd` to each word of a timing document. `True` means "start a new line after this word".
The rule is the same one the browser uses when a timing file has no flags (web/src/phrases.js), so old and new files draw alike:

  * a word ending in , ; : or a dash (also followed by closing quotes) ends a phrase when the line already has at least 3 words;
  * a sentence end (the sentence number changes, or the word ends with . ! ?) always ends a phrase;
  * a line never runs past 10 words. When flags are present the browser does not apply this cap itself, so it is applied here.

The word counter restarts after every break of any kind. Input words are never changed; new dicts are returned.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

MIN_WORDS = 3  # a comma only breaks a line that already has this many words
MAX_WORDS = 10  # a run with no punctuation never goes past this
_CLOSERS = "\"')”’"
_SOFT_END = re.compile(rf"[,;:—–][{re.escape(_CLOSERS)}]*$")
_HARD_END = re.compile(rf"[.!?][{re.escape(_CLOSERS)}]*$")


def phrase_ends(words: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return a new list of word dicts, each with a `phraseEnd` bool. The input is left untouched."""
    items = list(words)
    out: list[dict[str, Any]] = []
    on_line = 0
    for index, word in enumerate(items):
        on_line += 1
        text = str(word.get("text", ""))
        following = items[index + 1] if index + 1 < len(items) else None
        ends_sentence = following is None or following.get("sentence") != word.get("sentence") or bool(_HARD_END.search(text))
        ends_phrase = bool(_SOFT_END.search(text)) and on_line >= MIN_WORDS
        full = on_line >= MAX_WORDS
        breaks = ends_sentence or ends_phrase or full
        out.append({**word, "phraseEnd": breaks})
        if breaks:
            on_line = 0
    return out
