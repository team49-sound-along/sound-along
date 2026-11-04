"""Join the chunks of one long document into ONE passage: one audio file, one timing document, one set of cards, per language.

A long upload is narrated in chunks (each chunk fits the time limit of one generator run, 900 s on Lambda), but nobody ever sees a chunk: the chunks are
internal, and this module turns them into an ordinary passage with its own id, title and word times. Everything here is pure (no files, no network), so
the same code serves the local runner and the AWS generator.

What is joined, and how:
- audio: float samples, one pause (the paragraph gap, chunks end at paragraph breaks) between chunks; loudness is matched across chunks, then peak-normalised once.
- words: `i`, `start_ms`, `end_ms`, `sentence` and `paragraph` are shifted by what came before; the word times stay exact because the shift comes from the
  samples, not from rounded durations.
- metrics are summed, the review notes and vocabulary are combined, the title and fingerprint are the whole document's.
- translations: the sentence maps of every chunk are shifted and joined in both directions, so the language switch lands on the same sentence.
- cards are combined, first card wins.

A timing field this module does not know is an error, not something silently dropped.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from engine import SAMPLE_RATE
from mastering import level_match, peak_normalize

PARAGRAPH_GAP_S = 0.55  # the same pause the narration puts between paragraphs (pipeline.PARAGRAPH_GAP_S)

KNOWN_TIMING_KEYS = frozenset({
    "id", "title", "engine", "voice", "duration_ms", "metrics", "vocab", "words", "language", "generatedWith", "series", "review",
    "translations", "translationOf", "machineTranslated", "held",
})
SUMMED_METRICS = ("characters", "words", "audioSeconds", "generateSeconds", "unalignedWords", "pollyNeuralUsd", "pollyStandardUsd", "estimatedLambdaUsd")


@dataclass(frozen=True)
class Chunk:
    timing: dict[str, Any]
    audio: np.ndarray  # float32 mono at SAMPLE_RATE
    cards: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class Stitched:
    timing: dict[str, Any]
    audio: np.ndarray
    cards: Optional[dict[str, Any]]
    word_offsets: tuple[int, ...]  # first word index of every chunk
    sentence_offsets: tuple[int, ...]  # first sentence number of every chunk
    sentence_counts: tuple[int, ...]


def _sentence_count(timing: Mapping[str, Any]) -> int:
    return len({w["sentence"] for w in timing["words"]})


def _paragraph_count(timing: Mapping[str, Any]) -> int:
    return len({w["paragraph"] for w in timing["words"]})


def _check_known(timing: Mapping[str, Any]) -> None:
    if timing.get("pairId"):
        raise ValueError("a passage with a human recording is never split into chunks")
    unknown = set(timing) - KNOWN_TIMING_KEYS
    if unknown:
        raise ValueError(f"stitch does not know the timing field(s) {sorted(unknown)}: teach stitch.py how to join them before using them in a long document")


def _combine_metrics(chunks: Sequence[Chunk]) -> dict[str, Any]:
    first = chunks[0].timing.get("metrics") or {}
    total = {key: sum((c.timing.get("metrics") or {}).get(key, 0) for c in chunks) for key in SUMMED_METRICS if any(key in (c.timing.get("metrics") or {}) for c in chunks)}
    for key in ("audioSeconds", "generateSeconds", "pollyNeuralUsd", "pollyStandardUsd", "estimatedLambdaUsd"):
        if key in total:
            total[key] = round(total[key], 4 if key.endswith("Usd") else 2)
    audio, spent = total.get("audioSeconds") or 0, total.get("generateSeconds") or 0
    return {**{k: v for k, v in first.items() if k not in total}, **total, "realTimeFactor": round(spent / audio, 3) if audio else 0}


def stitch(chunks: Sequence[Chunk], passage_id: str, title: str, fingerprint: Optional[str] = None, gap_s: float = PARAGRAPH_GAP_S) -> Stitched:
    """One passage from the chunks, in order. The inputs are not changed."""
    if not chunks:
        raise ValueError("nothing to stitch")
    for chunk in chunks:
        _check_known(chunk.timing)
    language = {c.timing.get("language") or "en" for c in chunks}
    voice = {(c.timing.get("engine"), c.timing.get("voice")) for c in chunks}
    if len(language) != 1 or len(voice) != 1:
        raise ValueError("every chunk of a document must use the same language and voice")

    leveled = level_match([np.asarray(c.audio, dtype=np.float32) for c in chunks])
    gap = np.zeros(int(round(gap_s * SAMPLE_RATE)), dtype=np.float32)
    pieces: list[np.ndarray] = []
    words: list[dict[str, Any]] = []
    word_offsets, sentence_offsets, sentence_counts = [], [], []
    samples = 0
    n_words = n_sentences = n_paragraphs = 0
    for k, (chunk, audio) in enumerate(zip(chunks, leveled)):
        if k:
            pieces.append(gap)
            samples += len(gap)
        shift_ms = round(samples / SAMPLE_RATE * 1000)
        word_offsets.append(n_words)
        sentence_offsets.append(n_sentences)
        sentence_counts.append(_sentence_count(chunk.timing))
        for w in chunk.timing["words"]:
            words.append({**w, "i": w["i"] + n_words, "start_ms": w["start_ms"] + shift_ms, "end_ms": w["end_ms"] + shift_ms,
                          "sentence": w["sentence"] + n_sentences, "paragraph": w["paragraph"] + n_paragraphs})
        pieces.append(audio)
        samples += len(audio)
        n_words += len(chunk.timing["words"])
        n_sentences += sentence_counts[-1]
        n_paragraphs += _paragraph_count(chunk.timing)
    audio_all = peak_normalize(np.concatenate(pieces))

    first = chunks[0].timing
    generated_with = {**(first.get("generatedWith") or {}), **({"hash": fingerprint} if fingerprint else {})}
    suspects = [s for c in chunks for s in ((c.timing.get("review") or {}).get("suspects") or [])]
    vocab: dict[str, Any] = {}
    for c in chunks:
        for key, value in (c.timing.get("vocab") or {}).items():
            vocab.setdefault(key, copy.deepcopy(value))
    timing: dict[str, Any] = {
        "id": passage_id, "title": title, "engine": first.get("engine"), "voice": first.get("voice"),
        "duration_ms": round(len(audio_all) / SAMPLE_RATE * 1000), "metrics": _combine_metrics(chunks), "vocab": vocab, "words": words,
        "language": first.get("language") or "en", "generatedWith": generated_with,
    }
    if any(c.timing.get("review") for c in chunks):
        timing["review"] = {"source": (first.get("review") or {}).get("source", "asr-check"), "suspects": suspects}
    if first.get("machineTranslated"):
        timing["machineTranslated"] = True
    if first.get("held"):
        timing["held"] = True
    return Stitched(timing, audio_all, merge_cards([c.cards for c in chunks]), tuple(word_offsets), tuple(sentence_offsets), tuple(sentence_counts))


def merge_cards(documents: Sequence[Optional[Mapping[str, Any]]]) -> Optional[dict[str, Any]]:
    """The cards of every chunk as one document. A card that appears in several chunks keeps its first version."""
    docs = [d for d in documents if d]
    if not docs:
        return None
    merged: dict[str, Any] = {**copy.deepcopy(dict(docs[0]))}
    merged["words"], merged["places"] = {}, {}
    for doc in docs:
        for kind in ("words", "places"):
            for key, card in (doc.get(kind) or {}).items():
                merged[kind].setdefault(key, copy.deepcopy(card))
    figures = [f for doc in docs for f in (doc.get("figures") or [])]
    if figures:
        merged["figures"] = figures
    elif "figures" in merged:
        del merged["figures"]
    return merged


def link_translation(source: Stitched, target: Stitched, source_chunks: Sequence[Chunk], target_chunks: Sequence[Chunk], lang: str, source_lang: str,
                     source_id: str, target_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The two stitched timing documents with their links: the source's `translations[lang]` and the target's `translationOf`, both sentence maps rebuilt by
    shifting every chunk's map. Raises when the chunks do not line up (a chunk whose translation is missing means there is no translation at all)."""
    if len(source_chunks) != len(target_chunks):
        raise ValueError("every chunk needs its translation before the two languages can be linked")
    forward: list[list[int]] = []
    backward: list[int] = []
    for k, (src, dst) in enumerate(zip(source_chunks, target_chunks)):
        f = ((src.timing.get("translations") or {}).get(lang) or {}).get("sentenceMap")
        b = (dst.timing.get("translationOf") or {}).get("sentenceMap")
        if f is None or b is None or len(f) != source.sentence_counts[k] or len(b) != target.sentence_counts[k]:
            raise ValueError(f"chunk {k + 1}: the sentence maps do not match the sentences")
        forward += [[t + target.sentence_offsets[k] for t in group] for group in f]
        backward += [s + source.sentence_offsets[k] for s in b]
    linked_source = {**source.timing, "translations": {lang: {"id": target_id, "sentenceMap": forward}}}
    linked_target = {**target.timing, "machineTranslated": True, "translationOf": {"id": source_id, "lang": source_lang, "sentenceMap": backward}}
    return linked_source, linked_target


def retarget_ids(document: Any, old_ids: Sequence[str], new_id: str) -> Any:
    """A copy of a JSON document (cards) with every `/data/<old id>.` file reference pointing at `new_id` instead."""
    text = json.dumps(document, ensure_ascii=False)
    for old in old_ids:
        text = text.replace(f"/data/{old}.", f"/data/{new_id}.")
    return json.loads(text)
