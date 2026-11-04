"""Turn a ReadWorks passage's rendered HTML into stable, indexed word tokens.

Contract (see plan, "The data contract"):
  * Words come from the rendered ``content`` HTML, never from ``text``.
  * Figures, captions and image credits are skipped.
  * Vocab spans (``data-vocab-sense-id``) are preserved on the tokens they cover.
  * Every token gets a stable ``i`` index; sentences are numbered globally.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Optional

BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "li", "blockquote"}
SKIP_TAGS = {"figure", "figcaption", "script", "style"}
ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "st.", "jr.", "sr.", "vs.", "u.s.", "no.",
    "prof.", "rev.", "gen.", "col.", "sgt.", "capt.", "lt.", "hon.", "mt.", "ave.", "inc.", "co.", "corp.", "ltd.", "dept.", "approx.", "fig.", "vol.", "pp.", "p.", "cf.",
    "jan.", "feb.", "apr.", "aug.", "sep.", "sept.", "oct.", "nov.", "dec.",  # month abbreviations before a date
    "sra.", "srta.", "dra.", "ud.", "uds.", "av.", "pág.", "núm.",  # Spanish
    "lic.", "ing.", "arq.", "ee.", "cap.", "ej.", "aprox.", "tel.", "dpto.",
}
# Words that end with a period but only end the sentence when a capital letter follows ("in the EE. UU. y Canadá", "5 p. m. del jueves", "apples, etc. and pears").
CONTINUES_BEFORE_LOWERCASE = {"uu.", "m.", "etc."}
_CLOSERS = "\"')”’»"
_OPENERS = "\"'(“‘«¿¡—–-"
_DOTTED_REVERSED = re.compile(r"(?:\.[a-zñ]{1,2}){2,}", re.I)  # p.m. a.m. e.g. i.e., matched on the reversed word so a long run of dots stays linear
_TOKEN = re.compile(r"\S+")


@dataclass(frozen=True)
class Token:
    i: int
    text: str
    sentence: int
    paragraph: int
    vocab_sense_id: Optional[str] = None
    joined: bool = False  # no whitespace before this word: it continues the word before it ("good—" + "and"), so the page shows no space between them

    def to_dict(self) -> dict:
        data = {"i": self.i, "text": self.text, "sentence": self.sentence, "paragraph": self.paragraph}
        if self.joined:
            data["join"] = True
        if self.vocab_sense_id is not None:
            data["vocabId"] = self.vocab_sense_id
        return data


class _ParagraphCollector(HTMLParser):
    """Collects (text, vocab_sense_id) runs per block element, skipping figures."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[list[tuple[str, Optional[str]]]] = []
        self._current: Optional[list[tuple[str, Optional[str]]]] = None
        self._skip_depth = 0
        self._vocab_stack: list[Optional[str]] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in SKIP_TAGS:
            self._skip_depth += 1
        elif tag in BLOCK_TAGS and self._skip_depth == 0:
            self._current = []
        elif tag == "span":
            self._vocab_stack.append(dict(attrs).get("data-vocab-sense-id"))
        elif tag == "br" and self._current is not None:
            self._current.append((" ", None))

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in BLOCK_TAGS and self._current is not None:
            self.paragraphs.append(self._current)
            self._current = None
        elif tag == "span" and self._vocab_stack:
            self._vocab_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._current is None:
            return
        vocab = next((v for v in reversed(self._vocab_stack) if v), None)
        self._current.append((data, vocab))


def _starts_lowercase(word: Optional[str]) -> bool:
    letters = (word or "").lstrip(_OPENERS)
    return bool(letters) and letters[0].isalpha() and letters[0].islower()


def _ends_sentence(word: str, following: Optional[str] = None) -> bool:
    """Whether `word` closes a sentence. `following` is the next word of the same paragraph: a lowercase word after a dialogue tag's question or
    exclamation mark (\"Why?\" she asked) or after a dotted abbreviation (5 p.m. on Monday) continues the sentence."""
    core = word.lower().rstrip(_CLOSERS)
    if core in ABBREVIATIONS:
        return False
    if re.fullmatch(r"[A-Z]\.", word):  # initials such as "J."
        return False
    stripped = word.rstrip(_CLOSERS)
    if not stripped or stripped[-1] not in ".!?":  # a sentence mark, then only closing quotes or brackets (no regex: a long run of marks stays linear)
        return False
    if _starts_lowercase(following):
        if stripped[-1] in "?!":
            return False  # a dialogue tag
        if _DOTTED_REVERSED.match(core[::-1]) or core in CONTINUES_BEFORE_LOWERCASE:
            return False
    return True


_DASHES = "—–"  # em dash, en dash


def _split_on_dashes(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Split one whitespace-delimited chunk after any dash that sits between two characters.

    "good—and" becomes "good—" + "and", so a highlight covers one spoken word. A dash at either edge
    of the chunk is left alone ("—hello", "there—").
    """
    spans: list[tuple[int, int]] = []
    piece_start = start
    for pos in range(start + 1, end - 1):
        if text[pos] in _DASHES and text[pos + 1] not in _DASHES:
            spans.append((piece_start, pos + 1))
            piece_start = pos + 1
    spans.append((piece_start, end))
    return spans


def tokenize_html(content_html: str) -> list[Token]:
    """Return word tokens for ``content_html`` with stable indexes."""
    collector = _ParagraphCollector()
    collector.feed(content_html)
    collector.close()

    tokens: list[Token] = []
    sentence = 0
    for p_index, runs in enumerate(collector.paragraphs):
        text = "".join(chunk for chunk, _ in runs)
        vocab_by_char: list[Optional[str]] = []
        for chunk, vocab in runs:
            vocab_by_char.extend([vocab] * len(chunk))
        paragraph_has_tokens = False
        spans = [span for match in _TOKEN.finditer(text) for span in _split_on_dashes(text, match.start(), match.end())]
        for n, (start, end) in enumerate(spans):
            word = text[start:end]
            following = text[spans[n + 1][0]:spans[n + 1][1]] if n + 1 < len(spans) else None
            vocab = next((v for v in vocab_by_char[start:end] if v), None)
            tokens.append(Token(len(tokens), word, sentence, p_index, vocab, joined=n > 0 and spans[n - 1][1] == start))
            paragraph_has_tokens = True
            if _ends_sentence(word, following):
                sentence += 1
        if paragraph_has_tokens and (not tokens or tokens[-1].sentence == sentence):
            sentence += 1  # a paragraph always closes its last sentence
    return tokens


def sentences(tokens: list[Token]) -> list[str]:
    """Join tokens back into sentence strings for synthesis, in order."""
    grouped: dict[int, list[str]] = {}
    for token in tokens:
        grouped.setdefault(token.sentence, []).append(token.text)
    return [" ".join(words) for _, words in sorted(grouped.items())]
