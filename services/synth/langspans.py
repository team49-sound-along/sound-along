"""Find the stretches of a passage that must be SPOKEN in the other language (an English passage with El Salvador, a Spanish one with Halloween).

    detect_spans(text, base_lang) -> list[Span]     only spans whose language differs from base_lang; character offsets, end exclusive

Design, in order of how much each part is trusted (precision over recall: a wrong switch makes a right word sound wrong, a missed one is today's behaviour):
  1. Gazetteer (langspans_data.py): names, culture words and phrases that are only ever the other language ('El Salvador', 'abuela', 'Día de los
     Muertos', Halloween). One hit is enough. Spanish-origin names that US readers say in English (Los Angeles, Santa Fe, Colorado, Mexico) are
     listed as ENGLISH_READ and are never switched; the same list stops the article rule below from catching 'El Paso' or 'Las Vegas'.
  2. Spanish-only letters (ñ, -ción) make one word enough; other accents (á é í ó ú ü) and English letter patterns (th, sh, ck, wh, -ing) are weak
     cues that count only next to a stronger word.
  3. Article rule: Capitalised El/La/Los/Las/Del/De la (English: The) + a Capitalised word (+ 'de Capitalised' ...) is a name ('La Calabiuza').
  4. Function words: two or more neighbouring STRONG words ('buenos días', 'dónde está') form a span. Words that exist in both languages (a, me,
     no, sin, pan, red, come, he, sale, real, son) are SOFT: they may sit inside a span but never start or end one, so they never switch alone.
  5. A quoted sentence that is mostly the other language is covered whole, so one unknown word ('biblioteca') is not left behind in the wrong voice.
Never switched or crossed: respellings (kah-laa-bee-YOO-zah, also whole parentheses holding one), ALL-CAPS words (acronyms), words glued to digits,
anything across . ! ? ; : newline, parentheses or a quote mark. Spans cover whole words and exclude possessive 's, inverted marks and punctuation.
Everything is one pass of linear work (a regex tokenizer, dict lookups, bisect): no models, no network, no quadratic patterns.
MIXED_LANGUAGE=off (or 0/false/no) makes detect_spans return []."""
from __future__ import annotations

import os
import re
import unicodedata
from bisect import bisect_left
from dataclasses import dataclass
from typing import Optional

import langspans_data as D


@dataclass(frozen=True)
class Span:
    start: int  # character offset into the text
    end: int    # exclusive
    lang: str   # 'en' or 'es': the language this stretch should be SPOKEN in


@dataclass(frozen=True)
class _Lex:
    alone_words: frozenset
    alone_phrases: dict
    strong: frozenset
    soft: frozenset
    left_ok: frozenset
    loans: frozenset
    read_phrases: dict
    read_words: frozenset
    articles: frozenset
    connectors: frozenset


_LEX = {
    "es": _Lex(D.ES_ALONE_WORDS, D.ES_ALONE_PHRASES, D.ES_STRONG, D.ES_SOFT, D.ES_LEFT_OK, D.ES_LOANS,
               D.ES_ENGLISH_READ_PHRASES, D.ES_ENGLISH_READ_WORDS, D.ES_ARTICLES, D.ES_CONNECTORS),
    "en": _Lex(D.EN_ALONE_WORDS, D.EN_ALONE_PHRASES, D.EN_STRONG, D.EN_SOFT, D.EN_LEFT_OK, D.EN_LOANS,
               D.EN_ENGLISH_READ_PHRASES, D.EN_ENGLISH_READ_WORDS, D.EN_ARTICLES, D.EN_CONNECTORS),
}
_OFF_VALUES = {"off", "0", "false", "no", "disabled"}
_LETTER = r"(?:[^\W\d_]|[̀-ͯ])"
_TOKEN = re.compile(rf"{_LETTER}+(?:-{_LETTER}+)*")
_PAREN = re.compile(r"[()]")
_QUOTE = re.compile("[\"“”«»]")
_SPACES = " \t "
_BREAKS = frozenset(".!?…;:\n()[]")
_WEAK_ES = frozenset("áéíóúü")
_WEAK_EN = re.compile(r"th|sh|ck|wh|ough")
_MAX_SEP = 8
_MAX_PAREN = 120


def mixed_language_enabled() -> bool:
    """False when an operator set MIXED_LANGUAGE=off."""
    return os.environ.get("MIXED_LANGUAGE", "").strip().lower() not in _OFF_VALUES


def detect_spans(text: Optional[str], base_lang: Optional[str]) -> list[Span]:
    """Spans of `text` to speak in the language other than base_lang. Empty when unsure, disabled, or the input is odd."""
    try:
        if not isinstance(text, str) or not text.strip() or not mixed_language_enabled():
            return []
        base = _base(base_lang)
        if base is None:
            return []
        target = "es" if base == "en" else "en"
        return _detect(text, target)
    except Exception:  # never break narration over a heuristic
        return []


def _base(base_lang: object) -> Optional[str]:
    if not isinstance(base_lang, str):
        return None
    code = re.split(r"[-_]", base_lang.strip().lower(), maxsplit=1)[0]
    return code if code in ("en", "es") else None


def _norm(word: str) -> str:
    return unicodedata.normalize("NFC", word).lower()


def _is_respelling(word: str) -> bool:
    """kah-laa-bee-YOO-zah, WAH-kah: hyphenated syllables, a stressed ALL-CAPS part or three short lowercase ones."""
    if "-" not in word:
        return False
    parts = word.split("-")
    if any(len(p) >= 2 and p.isupper() for p in parts):
        return True
    return len(parts) >= 3 and all(len(p) <= 4 for p in parts)


def _capital(raw: str) -> bool:
    return raw[:1].isupper() and not raw.isupper()


class _Doc:
    """Tokens of one text plus the cheap separator tests between neighbours."""

    def __init__(self, text: str) -> None:
        self.text = text
        spans = [(m.start(), m.end()) for m in _TOKEN.finditer(text)]
        self.starts = [s for s, _ in spans]
        self.ends = [e for _, e in spans]
        self.raw = [text[s:e] for s, e in spans]
        self.low = [_norm(r) for r in self.raw]
        self.n = len(spans)

    def sep(self, i: int, j: int) -> str:
        """Text between token i and token j (j > i)."""
        return self.text[self.ends[i]:self.starts[j]]

    def spaced(self, i: int, j: int) -> bool:
        s = self.sep(i, j)
        return 0 < len(s) <= _MAX_SEP and not s.strip(_SPACES)

    def joined(self, i: int, j: int) -> bool:
        s = self.sep(i, j)
        return len(s) <= _MAX_SEP and s.strip(_SPACES) in ("", ",") and (len(s) > 0)


def _mark_ignored(doc: _Doc) -> list[bool]:
    ign = [False] * doc.n
    text = doc.text
    for i, raw in enumerate(doc.raw):
        s, e = doc.starts[i], doc.ends[i]
        glued = (s > 0 and (text[s - 1].isdigit() or text[s - 1] == "_")) or (
            e < len(text) and (text[e].isdigit() or text[e] == "_"))
        if glued or _is_respelling(raw) or (len(raw) >= 2 and raw.isupper()):
            ign[i] = True
    stack: list[int] = []
    for m in _PAREN.finditer(text):
        if m.group() == "(":
            stack.append(m.start())
            continue
        if not stack:
            continue
        opened = stack.pop()
        if m.start() - opened > _MAX_PAREN:
            continue
        lo, hi = bisect_left(doc.starts, opened), bisect_left(doc.starts, m.start())
        if any(_is_respelling(doc.raw[k]) for k in range(lo, hi)):
            for k in range(lo, hi):
                ign[k] = True
    return ign


def _match_phrases(doc: _Doc, table: dict, skip: list[bool]) -> list[tuple[int, int]]:
    """(first, last) token indexes of every phrase hit; phrases are space-separated words, longest first."""
    hits: list[tuple[int, int]] = []
    for i in range(doc.n):
        options = table.get(doc.low[i])
        if not options or skip[i]:
            continue
        for phrase in options:
            last = i
            for word in phrase[1:]:
                nxt = last + 1
                if nxt >= doc.n or doc.low[nxt] != word or skip[nxt] or not doc.spaced(last, nxt):
                    break
                last = nxt
            else:
                hits.append((i, last))
                break
    return hits


def _word_class(low: str, lex: _Lex, target: str) -> str:
    if low in lex.loans:
        return "N"
    if low in lex.alone_words:
        return "A"
    if target == "es":
        if "ñ" in low:
            return "A"
        if low.endswith(("ción", "sión", "ciones", "siones")):
            return "S"
    if low in lex.strong:
        return "S"
    if low in lex.soft:
        return "F"
    if target == "es" and any(c in _WEAK_ES for c in low):
        return "W"
    if target == "en" and (_WEAK_EN.search(low) or (low.endswith("ing") and len(low) >= 6)):
        return "W"
    return "N"


def _classify(doc: _Doc, lex: _Lex, target: str) -> list[str]:
    """One letter per token: A alone-enough, S strong, F soft, W weak cue, N nothing, B never switch, I ignored."""
    ign = _mark_ignored(doc)
    blocked = [False] * doc.n
    for a, b in _match_phrases(doc, lex.read_phrases, ign):
        for k in range(a, b + 1):
            blocked[k] = True
    for i, low in enumerate(doc.low):
        if low in lex.read_words:
            blocked[i] = True
    alone = [False] * doc.n
    for a, b in _match_phrases(doc, lex.alone_phrases, [x or y for x, y in zip(ign, blocked)]):
        for k in range(a, b + 1):
            alone[k] = True
    cls = []
    for i in range(doc.n):
        if ign[i]:
            cls.append("I")
        elif blocked[i]:
            cls.append("B")
        elif alone[i]:
            cls.append("A")
        else:
            cls.append(_word_class(doc.low[i], lex, target))
    _mark_name_groups(doc, lex, cls)
    return cls


def _mark_name_groups(doc: _Doc, lex: _Lex, cls: list[str]) -> None:
    """Capitalised article + Capitalised word (+ 'de Capitalised' ...) is a name: La Calabiuza, La Casa de Papel."""
    def free(k: int) -> bool:
        return k < doc.n and cls[k] not in "BI" and _capital(doc.raw[k])

    n = doc.n
    for i in range(n):
        if cls[i] in "BI" or doc.low[i] not in lex.articles and doc.low[i] != "de" or not _capital(doc.raw[i]):
            continue
        j = i + 1
        if doc.low[i] == "de":
            if not (j < n and doc.low[j] in ("la", "las", "los") and doc.spaced(i, j) and cls[j] not in "BI"):
                continue
            j += 1
        if not (j < n and doc.spaced(j - 1, j) and free(j)):
            continue
        last = j
        while True:
            k = last + 1
            if k >= n or not doc.spaced(last, k) or cls[k] in "BI":
                break
            if doc.low[k] in lex.connectors and k + 1 < n and doc.spaced(k, k + 1) and free(k + 1):
                last = k + 1
            elif doc.low[k] == "de" and k + 2 < n and doc.low[k + 1] in ("la", "las", "los") and doc.spaced(k, k + 1) \
                    and doc.spaced(k + 1, k + 2) and free(k + 2):
                last = k + 2
            else:
                break
        for k in range(i, last + 1):
            cls[k] = "A"


def _points(cls: list[str], lo: int, hi: int) -> int:
    return sum(2 if c == "A" else 1 if c == "S" else 0 for c in cls[lo:hi + 1])


def _runs(doc: _Doc, lex: _Lex, cls: list[str]) -> list[tuple[int, int]]:
    """Maximal chains of flagged tokens, trimmed of soft words at the edges, that carry at least two points."""
    out: list[tuple[int, int]] = []
    i, n = 0, doc.n
    while i < n:
        if cls[i] not in "ASFW":
            i += 1
            continue
        j = i
        while j + 1 < n and cls[j + 1] in "ASFW" and doc.joined(j, j + 1):
            j += 1
        lo, hi = i, j
        i = j + 1
        if cls[lo] == "F" and doc.low[lo] in lex.left_ok and lo < hi and cls[lo + 1] in "ASW":
            pass  # "mi amor", "San José": a soft opener is kept when a Spanish word follows
        else:
            while lo <= hi and cls[lo] == "F":
                lo += 1
        while hi >= lo and cls[hi] == "F":
            hi -= 1
        if lo <= hi and _points(cls, lo, hi) >= 2:
            out.append((lo, hi))
    return out


def _quote_ranges(text: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    opened: Optional[int] = None
    for m in _QUOTE.finditer(text):
        ch = m.group()
        if ch in "“«":
            opened = m.end()
        elif ch in "”»" or opened is not None:
            if opened is not None:
                out.append((opened, m.start()))
            opened = None
        else:
            opened = m.end()
    return out


def _quote_pieces(doc: _Doc, cls: list[str]) -> list[tuple[int, int]]:
    """Sentences inside quotes that are mostly the other language: (first, last) token indexes."""
    pieces: list[tuple[int, int]] = []
    for qs, qe in _quote_ranges(doc.text):
        lo, hi = bisect_left(doc.starts, qs), bisect_left(doc.starts, qe) - 1
        a = lo
        for k in range(lo, hi + 2):
            boundary = k > hi or any(c in _BREAKS for c in doc.sep(k - 1, k)) if k > lo else False
            if k > hi or boundary:
                end = k - 1
                if end >= a and _piece_ok(cls, a, end):
                    pieces.append((a, end))
                a = k
    return pieces


def _piece_ok(cls: list[str], a: int, b: int) -> bool:
    window = cls[a:b + 1]
    if "B" in window:
        return False
    eff = [c for c in window if c != "I"]
    if len(eff) < 2:
        return False
    flagged = sum(1 for c in eff if c in "ASFW")
    cov = flagged / len(eff)
    pts = _points(cls, a, b)
    return ((len(eff) >= 4 and cov >= 0.6) or cov >= 0.75) and (pts >= 2 or (pts >= 1 and cov == 1.0))


def _detect(text: str, target: str) -> list[Span]:
    doc = _Doc(text)
    if doc.n == 0:
        return []
    lex = _LEX[target]
    cls = _classify(doc, lex, target)
    found = _runs(doc, lex, cls) + _quote_pieces(doc, cls)
    found.sort(key=lambda r: (r[0], -r[1]))
    spans: list[Span] = []
    last_hi = -1
    for lo, hi in found:
        if lo > last_hi:
            spans.append(Span(doc.starts[lo], doc.ends[hi], target))
            last_hi = hi
    return spans
