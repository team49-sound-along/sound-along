"""One-off: build services/synth/word_definitions.json.gz from Open English WordNet (CC BY 4.0) and a plain-text corpus.

    python scripts/build_word_definitions.py --wordnet english-wordnet-2025.xml.gz --corpus a.txt b.txt --out services/synth/word_definitions.json.gz

Table: {"words": {lemma: {pos: [[definition, example, pronunciation], ...]}}, "common": [lemma, ...]}. Only single, lower-case, alphabetic words; up to three
senses of each part of speech (WordNet lists the most frequent first). `common` is the most frequent content words of the corpus: words a
child already knows, which get no definition card. Source: https://en-word.net/downloads (licence in NOTICE.md).
"""
from __future__ import annotations

import argparse
import collections
import gzip
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "synth"))
from word_definitions import short_gloss  # noqa: E402

POS = {"n": "n", "v": "v", "a": "a", "s": "a", "r": "r"}
WORD = re.compile(r"^[a-z]{3,20}$")
COMMON_COUNT = 2000
SENSES = 3  # the most frequent senses; the right one is chosen from the passage (word_definitions.py)


def parse_wordnet(stream: Any) -> dict[str, dict[str, list[str]]]:
    """lemma -> pos -> [[definition, example, pronunciation], ...] (up to 3 senses) from a WN-LMF file."""
    synsets: dict[str, tuple[str, str]] = {}
    entries: list[tuple[str, str, list[str], str]] = []  # lemma, pos, synset ids in sense order, ipa
    for _, el in ET.iterparse(stream, events=("end",)):
        tag = el.tag.split("}")[-1]
        if tag == "Synset":
            d = el.find("Definition")
            e = el.find("Example")
            synsets[el.get("id")] = ((d.text or "").strip() if d is not None else "", (e.text or "").strip() if e is not None else "")
            el.clear()
        elif tag == "LexicalEntry":
            lemma = el.find("Lemma")
            senses = [x.get("synset") for x in el.findall("Sense")]
            if lemma is not None and senses:
                ipa = next((p.text for p in lemma.findall("Pronunciation") if p.get("variety") == "US"), None) or next((p.text for p in lemma.findall("Pronunciation")), "")
                entries.append((lemma.get("writtenForm"), lemma.get("partOfSpeech"), senses, ipa or ""))
            el.clear()
    table: dict[str, dict[str, list[str]]] = {}
    for written, pos, senses, ipa in entries:
        letter = POS.get(pos)
        if not letter or not WORD.match(written):
            continue
        found = [[short_gloss(synsets[sid][0]), synsets[sid][1][:110], ipa] for sid in senses[:SENSES] if sid in synsets and synsets[sid][0]]
        if found:
            table.setdefault(written, {}).setdefault(letter, found)
    return table


def common_words(texts: Iterable[str], count: int = COMMON_COUNT) -> list[str]:
    import spacy

    nlp = spacy.load("en_core_web_sm", disable=["parser", "ner"])
    nlp.max_length = 5_000_000
    seen: collections.Counter[str] = collections.Counter()
    for text in texts:
        for t in nlp(text):
            if t.pos_ in ("NOUN", "VERB", "ADJ", "ADV") and WORD.match(t.lemma_.lower()):
                seen[t.lemma_.lower()] += 1
    return [w for w, _ in seen.most_common(count)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wordnet", required=True)
    ap.add_argument("--corpus", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with gzip.open(args.wordnet, "rb") as f:
        table = parse_wordnet(f)
    common = common_words(Path(p).read_text(encoding="utf-8", errors="ignore") for p in args.corpus)
    with gzip.open(args.out, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump({"source": "Open English WordNet 2025, CC BY 4.0, https://en-word.net", "words": table, "common": common}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(table)} words, {len(common)} common, {Path(args.out).stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
