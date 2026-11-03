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
    "mr.", "mrs.", "ms.", "dr.", "st.", "jr.", "sr.", "vs.", "etc.", "u.s.", "no.",
    "sra.", "srta.", "dra.", "ud.", "uds.", "av.", "pág.", "núm.",  # Spanish
}
_SENTENCE_END = re.compile(r"[.!?]+[\"')”’]*$")
_TOKEN = re.compile(r"\S+")


@dataclass(frozen=True)
class Token:
    i: int
    text: str
    sentence: int
    paragraph: int
    vocab_sense_id: Optional[str] = None

    def to_dict(self) -> dict:
        data = {"i": self.i, "text": self.text, "sentence": self.sentence, "paragraph": self.paragraph}
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


def _ends_sentence(word: str) -> bool:
    if word.lower() in ABBREVIATIONS:
        return False
    if re.fullmatch(r"[A-Z]\.", word):  # initials such as "J."
        return False
    return bool(_SENTENCE_END.search(word))


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
        for match in _TOKEN.finditer(text):
            for start, end in _split_on_dashes(text, match.start(), match.end()):
                word = text[start:end]
                vocab = next((v for v in vocab_by_char[start:end] if v), None)
                tokens.append(Token(len(tokens), word, sentence, p_index, vocab))
                paragraph_has_tokens = True
                if _ends_sentence(word):
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
