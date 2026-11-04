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
# for passages up to BIG_MAX_WORDS only. Measured in the image with 2 CPUs and 4 GB: 0.20 s/word (small: 0.08). With narration at about 0.48 s/word, 900 words
# is about 180 s + 430 s, inside the 900 s Lambda limit with a third to spare. Not yet measured on Lambda itself.
BIG: dict[tuple[str, str], tuple[str, str]] = {("en", "es"): ("Helsinki-NLP/opus-mt-tc-big-en-es", "8f4d4924189681076e9c642b2fd85278d793fd4d")}  # CC-BY-4.0
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
def _translate_all(texts: list[str], model: TranslateFn) -> list[str]:
    out: list[str] = []
    for start in range(0, len(texts), BATCH):
        chunk = texts[start:start + BATCH]
        got = model(chunk)
        if len(got) != len(chunk):
            raise ValueError("the translator returned the wrong number of sentences")
        out += got
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
        first = restore_names([m for m, _ in masked], first)
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
        results.append(restored if _END.search(restored) else restored + ".")

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
        marian = MarianMTModel.from_pretrained(where, **kwargs).eval()

        def translate(texts: list[str]) -> list[str]:
            batch = tokenizer(texts, return_tensors="pt", padding=True, truncation=True, max_length=256)
            with torch.no_grad():
                ids = marian.generate(**batch, num_beams=4, max_new_tokens=256)
            out = tokenizer.batch_decode(ids, skip_special_tokens=True)
            return [fix_possessive(s, plain_register(t)) for s, t in zip(texts, out)] if target == "en" else out

        _MODELS[key] = translate
        return translate
