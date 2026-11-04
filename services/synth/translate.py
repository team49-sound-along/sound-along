"""Translate a passage between English and Spanish, sentence by sentence, with free open models (Helsinki-NLP Opus-MT, Apache-2.0).

Design (each point was tested against the real model):
  * One source sentence at a time, paragraphs kept, so the reader can keep its place when switching language: `sentence_map[i]` lists the target
    sentence numbers that source sentence i became (a translation can split one sentence into two).
  * Place names are MASKED before translation (the model turned "Piedmont Park" into "Parque Piamonte") and restored exactly afterwards. If a model
    still loses a placeholder, that sentence is translated again unmasked and its number is recorded in `unprotected`, never shipped silently.
  * A translated sentence always ends with sentence punctuation, so sentence numbering cannot drift.
Machine translation: it is labelled as such in the product and a Spanish speaker should review it. Standard library plus transformers/sentencepiece (lazy).
"""
from __future__ import annotations

import html as html_lib
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from pipeline import tokenize_html

# (source, target) -> (model repo, full commit hash). Both are Apache-2.0 and ungated. The Docker image bakes exactly these.
PAIRS: dict[tuple[str, str], tuple[str, str]] = {
    ("en", "es"): ("Helsinki-NLP/opus-mt-en-es", "5bc4493d463cf000c1f0b50f8d56886a392ed4ab"),
    ("es", "en"): ("Helsinki-NLP/opus-mt-es-en", "c96e2c5399ebfae4fc43d9669556b9afa74bb69d"),
}
# A larger model reads better (the small one said "mucho" for "a great deal"; this one says "un gran negocio") but is about three times slower, so it is used
# for passages up to BIG_MAX_WORDS only. Measured in the image with 2 CPUs and 4 GB: English to Spanish 0.195 s/word (small 0.065), Spanish to English 0.29 s/word
# (small 0.11). With narration at about 0.45 s/word, 900 words is at worst about 260 s + 405 s = 665 s of the 900 s Lambda limit. Not yet measured on Lambda itself.
BIG: dict[tuple[str, str], tuple[str, str]] = {
    ("en", "es"): ("Helsinki-NLP/opus-mt-tc-big-en-es", "8f4d4924189681076e9c642b2fd85278d793fd4d"),  # CC-BY-4.0
    # Romance languages to English (Spanish included), Apache-2.0. On literary Spanish it fixes many errors of the small model ("zabacha mirrors" -> "jet mirrors",
    # "cotton sugar" -> "cotton candy", "Pedro" kept) at about twice the time.
    ("es", "en"): ("Helsinki-NLP/opus-mt-tc-bible-big-roa-en", "4d4757865ab116b39daa3b4ca3cfe1e7daf43cbe"),
}
BIG_MAX_WORDS = 900
BATCH = 16
_END = re.compile(r"[.!?…][\"')”’»]*$")
TranslateFn = Callable[[list[str]], list[str]]


@dataclass(frozen=True)
class Translated:
    title: str
    content_html: str
    sentence_map: list[list[int]]  # source sentence i -> target sentence numbers
    unprotected: list[int]  # source sentence numbers whose place names could not be protected
    localized: dict[str, str] = field(default_factory=dict)  # place name -> its name in the target language (Great Britain -> Gran Bretaña)


# ---- placeholders ----------------------------------------------------------------------------------------------------------------
def _placeholder(n: int) -> str:
    letters = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        letters = chr(97 + r) + letters
    return f"Xq{letters}x"


def mask(text: str, names: Sequence[str]) -> tuple[str, dict[str, str]]:
    """Replace each name that appears (whole words, longest first) with a placeholder the model leaves alone. Returns (masked text, placeholder -> name)."""
    table: dict[str, str] = {}
    for name in sorted({n for n in names if n}, key=len, reverse=True):
        pattern = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)")
        if pattern.search(text):
            placeholder = _placeholder(len(table))
            text = pattern.sub(placeholder, text)
            table[placeholder] = name
    return text, table


def unmask(text: str, table: dict[str, str]) -> str:
    for placeholder in sorted(table, key=len, reverse=True):
        text = text.replace(placeholder, table[placeholder])
    return text


# ---- the passage -----------------------------------------------------------------------------------------------------------------
# Marian models were trained on sentences of ordinary length. A long sentence is cut short without any error (the larger English to Spanish model turned a
# 112-word sentence into 86 words and lost its ending) or the model loops on it. So long sentences are translated in clause-sized pieces, and any translation
# whose length is implausible is retried in smaller pieces.
LONG_WORDS = 40
PIECE_WORDS = 26
RETRY_PIECE_WORDS = 14
MIN_RATIO, MAX_RATIO = 0.55, 2.4  # words out / words in; English <-> Spanish normally gives 0.85 to 1.25
_CLAUSE_BREAK = re.compile(r"(?<=[,;:—–])\s+|\s+(?=—)")


def split_pieces(text: str, size: int) -> list[str]:
    """Cut a long sentence at commas, semicolons, colons and dashes into pieces of about `size` words; a stretch with no punctuation is cut by words."""
    clauses = [c for c in _CLAUSE_BREAK.split(text) if c.strip()]
    pieces: list[str] = []
    current: list[str] = []
    for clause in clauses:
        words = clause.split()
        if current and len(current) + len(words) > size:
            pieces.append(" ".join(current))
            current = []
        while len(words) > size:  # no punctuation to cut at
            pieces.append(" ".join(words[:size]))
            words = words[size:]
        current += words
    if current:
        pieces.append(" ".join(current))
    return pieces


def _fit_piece(source: str, translated: str, first: bool, last: bool) -> str:
    """A piece translated on its own comes back as a sentence (capital first letter, full stop). Put it back the way it stood inside the sentence."""
    translated = translated.strip()
    if not first and source[:1].islower() and translated[:1].isupper() and not translated[1:2].isupper():
        translated = translated[:1].lower() + translated[1:]
    if not last and not re.search(r"[.!?…]$", source.rstrip("\"')”’»")) and translated.endswith("."):
        translated = translated[:-1]
    return translated


def _translate_pieces(text: str, model: TranslateFn, size: int) -> str:
    pieces = split_pieces(text, size)
    if len(pieces) < 2:
        return model([text])[0]
    got = model(pieces)
    if len(got) != len(pieces):
        raise ValueError("the translator returned the wrong number of sentences")
    return " ".join(_fit_piece(p, g, i == 0, i == len(pieces) - 1) for i, (p, g) in enumerate(zip(pieces, got)))


def _plausible(source: str, translated: str) -> bool:
    n = len(source.split())
    return n < 8 or MIN_RATIO <= len(translated.split()) / n <= MAX_RATIO


def _translate_all(texts: list[str], model: TranslateFn) -> list[str]:
    out: list[str] = [""] * len(texts)
    whole = [i for i, t in enumerate(texts) if len(t.split()) <= LONG_WORDS]
    for start in range(0, len(whole), BATCH):
        idx = whole[start:start + BATCH]
        got = model([texts[i] for i in idx])
        if len(got) != len(idx):
            raise ValueError("the translator returned the wrong number of sentences")
        for i, g in zip(idx, got):
            out[i] = g
    for i, t in enumerate(texts):
        if len(t.split()) > LONG_WORDS:
            out[i] = _translate_pieces(t, model, PIECE_WORDS)
    for i, t in enumerate(texts):  # a length that cannot be right: try again in smaller pieces
        if not _plausible(t, out[i]):
            retry = _translate_pieces(t, model, RETRY_PIECE_WORDS)
            if _plausible(t, retry) or abs(len(retry.split()) - len(t.split())) < abs(len(out[i].split()) - len(t.split())):
                out[i] = retry
    return out


def _sentence_count(text: str) -> int:
    return max(1, len({t.sentence for t in tokenize_html(f"<p>{html_lib.escape(text, quote=False)}</p>")}))


def translate_passage(passage: dict[str, Any], model: TranslateFn, names_fn: Callable[[str], list[str]],
                      localize: Optional[Callable[[list[str]], Any]] = None) -> Translated:
    """Translate title and text. `names_fn(plain_text)` returns the place names to protect (spaCy places for English; capitalised names otherwise)."""
    tokens = tokenize_html(passage.get("content") or "")
    if not tokens:
        raise ValueError("The passage has no readable text.")
    plain = " ".join(t.text for t in tokens)
    names = [n for n in names_fn(plain) if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", plain)]

    order: list[int] = []
    text_of: dict[int, str] = {}
    paragraph_of: dict[int, int] = {}
    for t in tokens:
        if t.sentence not in text_of:
            order.append(t.sentence)
            text_of[t.sentence] = ""
            paragraph_of[t.sentence] = t.paragraph
        text_of[t.sentence] = (text_of[t.sentence] + " " + t.text).strip()
    if order != list(range(len(order))):
        raise ValueError("sentence numbers are not contiguous; cannot build a sentence map")

    try:
        local: dict[str, str] = dict(localize(names)) if (localize and names) else {}
    except Exception:  # noqa: BLE001 (offline or garbage: keep the original names)
        local = {}
    # A single-word place with no local name ("Britain") is left to the model, which translates well-known places correctly; restoring the
    # English word would leave "a Britain" in the Spanish text. Names with a local name, and longer names ("Piedmont Park"), stay protected.
    protect = [n for n in names if n in local or len(n.split()) > 1]
    masked = [mask(text_of[i], protect) for i in order]
    first = _translate_all([m for m, _ in masked], model)
    if not protect:  # names were left to the model: keep each character's name the same in every sentence
        first = restore_translated_names([m for m, _ in masked], restore_names([m for m, _ in masked], first))
    results: list[str] = []
    unprotected: list[int] = []
    for i, (raw, (_, table)) in zip(order, zip(first, masked)):
        if table and not all(raw.count(p) == 1 for p in table):
            raw = _translate_all([text_of[i]], model)[0]  # translate again with the real names; record that protection failed
            unprotected.append(i)
            restored = raw
        else:
            restored = unmask(raw, {p: local.get(n, n) for p, n in table.items()})
        restored = " ".join(restored.split())
        # A sentence needs closing punctuation so the sentence numbers stay stable. A source that ends with ; : or , (the last sentence of a paragraph that stops
        # there) keeps that ending; adding a full stop would give ";."
        soft_source = bool(re.search(r"[;:,]$", text_of[i].rstrip()))
        results.append(restored if _END.search(restored) or (soft_source and re.search(r"[;:,]$", restored)) else restored + ".")

    title = _translate_all([passage.get("title") or ""], model)[0] if passage.get("title") else ""
    paragraphs: dict[int, list[str]] = {}
    for i, text in zip(order, results):
        paragraphs.setdefault(paragraph_of[i], []).append(html_lib.escape(text, quote=False))
    content = "".join(f"<p>{' '.join(parts)}</p>" for _, parts in sorted(paragraphs.items()))

    sentence_map: list[list[int]] = []
    cursor = 0
    for text in results:
        n = _sentence_count(text)
        sentence_map.append(list(range(cursor, cursor + n)))
        cursor += n
    if cursor != len({t.sentence for t in tokenize_html(content)}):
        raise ValueError("the translated sentence count does not match the sentence map")
    return Translated(title=title, content_html=content, sentence_map=sentence_map, unprotected=unprotected, localized=local)


# ---- the real model --------------------------------------------------------------------------------------------------------------
_MODELS: dict[tuple[str, str, bool], TranslateFn] = {}
_LOCK = threading.Lock()


_SU = re.compile(r"\bsus?\b", re.I)
_FORMAL = re.compile(r"\b(usted|ustedes|tú|tu|tus|ti|contigo|vosotros|vuestro|vuestra|vuestros|vuestras)\b", re.I)
_YOUR = re.compile(r"\b(your|yours)\b")


def fix_possessive(source: str, translated: str) -> str:
    """Spanish su/sus means his, her or their in a story; the model sometimes writes "your" ("close to your house"). When the Spanish has su/sus and
    nothing addressing a reader (usted, tú ...), "your" is wrong, and "their" is the safe reading."""
    if _SU.search(source) and not _FORMAL.search(source) and _YOUR.search(translated):
        return _YOUR.sub(lambda m: "theirs" if m.group(1) == "yours" else "their", translated)
    return translated


def _caps(sentence: str) -> list[str]:
    """Capitalised words that are not the first word of the sentence (the first is capitalised anyway)."""
    return [w for w in re.findall(r"(?<!^)(?<=\s)([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñü]+)", " ".join(sentence.split()))]


# Common first names that models translate. Spanish form -> English forms. Names that are also ordinary words (Rosa, Pilar, Sol, Mar, Grace) are left out on purpose.
_NAME_PAIRS = {
    "Juan": ["John"], "Pedro": ["Peter"], "José": ["Joseph", "Joe"], "Carlos": ["Charles", "Carl"], "Luis": ["Louis", "Lewis"], "Miguel": ["Michael"], "Pablo": ["Paul"],
    "Jorge": ["George"], "Francisco": ["Francis", "Frank"], "Santiago": ["James"], "Antonio": ["Anthony", "Tony"], "Eduardo": ["Edward"], "Ricardo": ["Richard"],
    "Guillermo": ["William"], "Fernando": ["Ferdinand"], "Rafael": ["Raphael"], "Alejandro": ["Alexander"], "Diego": ["James"], "Andrés": ["Andrew"], "Mateo": ["Matthew"],
    "Marta": ["Martha"], "Sara": ["Sarah"], "Lucía": ["Lucy"], "Juana": ["Joan", "Joanna", "Jane"], "Catalina": ["Catherine", "Katherine"], "Margarita": ["Margaret"],
    "Teresa": ["Theresa", "Teresa"], "Isabel": ["Isabelle", "Elizabeth"], "Elena": ["Helen", "Ellen"], "Sofía": ["Sophia", "Sophie"], "Ana": ["Anne", "Anna", "Ann"],
    "María": ["Mary", "Maria"], "Carolina": ["Caroline"], "Victoria": ["Victoria"], "Beatriz": ["Beatrice"], "Alicia": ["Alice"], "Julia": ["Julie"],
}
_EQUIVALENTS: dict[str, set[str]] = {}
for _es, _ens in _NAME_PAIRS.items():
    _EQUIVALENTS.setdefault(_es, set()).update(_ens)
    for _en in _ens:
        _EQUIVALENTS.setdefault(_en, set()).add(_es)


def _skeleton(name: str) -> str:
    """A name without accents, capitals or doubled letters: Anna, Ana and Aná share one skeleton, so do Lucia and Lucía."""
    import unicodedata

    plain = "".join(c for c in unicodedata.normalize("NFD", name.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"(.)\1+", r"\1", plain)


def restore_translated_names(sources: list[str], outputs: list[str]) -> list[str]:
    """Put back a first name that a model respelled or translated (Anna for Ana, Lucia for Lucía, Peter for Pedro). Acts only when the name is missing from the
    sentence's translation and an equivalent is there: a respelling with the same skeleton, or a pair from _NAME_PAIRS."""
    result = []
    for s, o in zip(sources, outputs):
        names = [w for w in re.findall(r"[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñü]+", s)]
        for name in names:
            if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", o):
                continue
            candidates = set(_EQUIVALENTS.get(name, ()))
            candidates |= {w for w in re.findall(r"[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñü]+", o) if _skeleton(w) == _skeleton(name) and w != name and w not in s}
            for variant in sorted(candidates, key=len, reverse=True):
                pattern = re.compile(rf"(?<!\w){re.escape(variant)}(?!\w)")
                if pattern.search(o):
                    o = pattern.sub(name, o, count=1)
                    break
        result.append(o)
    return result


def restore_names(sources: list[str], outputs: list[str]) -> list[str]:
    """Keep a character's name the same in every sentence. A model sometimes translates a first name in one sentence (Pablo -> Paul) and leaves it in
    another. A name counts as confirmed only when the model kept it unchanged somewhere; then, in a sentence where that one name vanished and exactly one
    new capitalised word appeared in its place, the confirmed name is put back. Anything less certain is left alone (Estados Unidos -> United States)."""
    kept = {w for s, o in zip(sources, outputs) for w in _caps(s) if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", o)}
    result = []
    for s, o in zip(sources, outputs):
        src_caps = _caps(s)
        missing = [w for w in src_caps if w in kept and not re.search(rf"(?<!\w){re.escape(w)}(?!\w)", o)]
        extra = [w for w in _caps(o) if w not in src_caps and len(w) > 1]
        if len(missing) == 1 and len(extra) == 1:
            o = re.sub(rf"(?<!\w){re.escape(extra[0])}(?!\w)", missing[0], o, count=1)
        result.append(o)
    return result


_ENDS_Q = re.compile(r"\?[\"')”’»]*$")
_ENDS_X = re.compile(r"![\"')”’»]*$")
_LEAD = re.compile(r"^[\s\"'(“‘«—–-]*")


def add_spanish_marks(text: str) -> str:
    """Spanish opens a question with ¿ and an exclamation with ¡. A model sometimes writes only the closing mark (especially in a long sentence);
    the opening mark goes at the start of the sentence (after a quote or dash), which is right for a sentence that is wholly a question or exclamation."""
    for closing, opening, ends in (("?", "¿", _ENDS_Q), ("!", "¡", _ENDS_X)):
        if ends.search(text) and opening not in text:
            lead = _LEAD.match(text).end()
            text = text[:lead] + opening + text[lead:]
    return text


def balance_quotes(text: str) -> str:
    """The larger Spanish to English model sometimes drops the closing quotation mark at the end of a sentence; add it back."""
    if text.count("\u201C") > text.count("\u201D"):
        text += "\u201D"
    elif text.count('"') % 2 == 1:
        text += '"'
    return text


def word_count(content_html: str) -> int:
    """Number of spoken words in a passage, counted exactly as the reader counts them."""
    return len(tokenize_html(content_html or ""))


_SLANG = {"gonna": "going to", "wanna": "want to", "gotta": "have to", "kinda": "kind of", "sorta": "sort of", "lemme": "let me", "gimme": "give me", "dunno": "do not know"}
_SLANG_RE = re.compile(r"\b(" + "|".join(_SLANG) + r")\b", re.I)


def plain_register(text: str) -> str:
    """Opus-MT often picks casual English ("they're gonna"). A reader for children gets the full form. Keeps the capital of a sentence start."""
    def fix(m: "re.Match[str]") -> str:
        full = _SLANG[m.group(1).lower()]
        return full[0].upper() + full[1:] if m.group(1)[0].isupper() else full

    return _SLANG_RE.sub(fix, text)


def use_big(source: str, target: str, words: Optional[int]) -> bool:
    """The larger model, for a known passage length up to BIG_MAX_WORDS, where one exists. TRANSLATE_BIG=off turns it off."""
    return (words is not None and 0 < words <= BIG_MAX_WORDS and (source, target) in BIG
            and os.environ.get("TRANSLATE_BIG", "on").strip().lower() not in ("off", "0", "false", "no"))


def load_model(source: str, target: str, words: Optional[int] = None) -> TranslateFn:
    """The Opus-MT translator for a language pair. TRANSLATE_MODELS_DIR (baked into the Lambda image) is read with local_files_only, so nothing is
    downloaded at run time there; otherwise the pinned revision is fetched and cached. Loaded once per process.
    `words` is the passage length: a short passage gets the larger model where there is one (see BIG)."""
    if (source, target) not in PAIRS:
        raise ValueError("Translation is available for en to es or es to en.")
    big = use_big(source, target, words)
    key = (source, target, big)
    with _LOCK:
        if key in _MODELS:
            return _MODELS[key]
        import torch
        from transformers import MarianMTModel, MarianTokenizer

        repo, revision = BIG[(source, target)] if big else PAIRS[(source, target)]
        baked = os.environ.get("TRANSLATE_MODELS_DIR")
        folder = f"{source}-{target}" + ("-big" if big else "")
        where, kwargs = (os.path.join(baked, folder), {"local_files_only": True}) if baked else (repo, {"revision": revision})
        tokenizer = MarianTokenizer.from_pretrained(where, **kwargs)
        # Always full precision: transformers 5 loads weights in the dtype they are stored in, and a half-precision model runs about 5 times slower on a CPU
        # (20 s against 4 s for the same 30 sentences, identical output). Storing weights in half precision on disk (see bake_model.py) is fine.
        marian = MarianMTModel.from_pretrained(where, dtype=torch.float32, **kwargs).eval()

        def translate(texts: list[str]) -> list[str]:
            batch = tokenizer(texts, return_tensors="pt", padding=True, truncation=True, max_length=256)
            with torch.no_grad():
                ids = marian.generate(**batch, num_beams=4, max_new_tokens=256)
            out = tokenizer.batch_decode(ids, skip_special_tokens=True)
            return [balance_quotes(fix_possessive(s, plain_register(t))) for s, t in zip(texts, out)] if target == "en" else [add_spanish_marks(t) for t in out]

        _MODELS[key] = translate
        return translate
