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
    masked = [mask(text_of[i], names) for i in order]
    first = _translate_all([m for m, _ in masked], model)
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
_MODELS: dict[tuple[str, str], TranslateFn] = {}
_LOCK = threading.Lock()


def load_model(source: str, target: str) -> TranslateFn:
    """The Opus-MT translator for a language pair. TRANSLATE_MODELS_DIR (baked into the Lambda image) is read with local_files_only, so nothing is
    downloaded at run time there; otherwise the pinned revision is fetched and cached. Loaded once per process."""
    if (source, target) not in PAIRS:
        raise ValueError("Translation is available for en to es or es to en.")
    with _LOCK:
        if (source, target) in _MODELS:
            return _MODELS[(source, target)]
        import torch
        from transformers import MarianMTModel, MarianTokenizer

        repo, revision = PAIRS[(source, target)]
        baked = os.environ.get("TRANSLATE_MODELS_DIR")
        where, kwargs = (os.path.join(baked, f"{source}-{target}"), {"local_files_only": True}) if baked else (repo, {"revision": revision})
        tokenizer = MarianTokenizer.from_pretrained(where, **kwargs)
        marian = MarianMTModel.from_pretrained(where, **kwargs).eval()

        def translate(texts: list[str]) -> list[str]:
            batch = tokenizer(texts, return_tensors="pt", padding=True, truncation=True, max_length=256)
            with torch.no_grad():
                ids = marian.generate(**batch, num_beams=4, max_new_tokens=256)
            return tokenizer.batch_decode(ids, skip_special_tokens=True)

        _MODELS[(source, target)] = translate
        return translate
