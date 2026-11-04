"""Passage -> audio + word timing. Pure orchestration over the parser, an Engine and the word mapper.

Stages (reported through ``on_step``): parse -> synthesize -> align -> publish (publish is done by the caller).
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "parse"))

from engine import SAMPLE_RATE, Engine, SentenceAudio, concat, silence  # noqa: E402
from mastering import fade_edges, level_match, peak_normalize  # noqa: E402
from tokenizer import Token, tokenize_html  # noqa: E402
from word_mapper import map_words  # noqa: E402

SENTENCE_GAP_S = 0.25
PARAGRAPH_GAP_S = 0.55

StepCallback = Callable[[str], None]


@dataclass(frozen=True)
class Generated:
    audio: np.ndarray
    words: tuple[dict[str, Any], ...]
    seconds_of_audio: float
    seconds_to_generate: float
    characters: int
    unaligned_words: int


def _group_by_sentence(tokens: list[Token]) -> list[list[Token]]:
    groups: dict[int, list[Token]] = {}
    for token in tokens:
        groups.setdefault(token.sentence, []).append(token)
    return [groups[key] for key in sorted(groups)]


def _noop(_: str) -> None:
    return None


MAX_WORDS_PER_MINUTE = 330  # people read aloud at 100 to 200; far beyond this the engine dropped part of the text
MIN_WORDS_JUDGED = 40


def check_pace(words: int, seconds: float) -> None:
    """An engine can cut a long sentence off without any error. Publishing narration that stops after a fraction of the text would be worse than a failed job."""
    if words >= MIN_WORDS_JUDGED and seconds > 0 and words / (seconds / 60) > MAX_WORDS_PER_MINUTE:
        raise ValueError(f"The narration came out too short for {words} words ({seconds:.0f} s); part of the text was not spoken.")


def generate(content_html: str, engine: Engine, on_step: StepCallback = _noop) -> Generated:
    started = time.perf_counter()

    on_step("parse")
    tokens = tokenize_html(content_html)
    groups = _group_by_sentence(tokens)
    if not groups:
        raise ValueError("The passage has no readable text.")

    on_step("synthesize")
    spoken_by_group: list[SentenceAudio] = [engine.synthesize(" ".join(t.text for t in g)) for g in groups]

    on_step("align")
    # Mastering changes gain and the first/last few ms only, so the timings below stay exact.
    mastered = [fade_edges(a) for a in level_match([s.audio for s in spoken_by_group])]
    parts: list[np.ndarray] = []
    words: list[dict[str, Any]] = []
    clock = 0.0
    previous_paragraph = None
    characters = 0
    for group, spoken, sentence_audio in zip(groups, spoken_by_group, mastered):
        characters += len(" ".join(t.text for t in group))
        if previous_paragraph is not None:
            gap = PARAGRAPH_GAP_S if group[0].paragraph != previous_paragraph else SENTENCE_GAP_S
            parts.append(silence(gap))
            clock += gap
        previous_paragraph = group[0].paragraph

        mapped = map_words([t.text for t in group], spoken.tokens)
        for token, word in zip(group, mapped):
            entry: dict[str, Any] = {
                "i": token.i,
                "text": token.text,
                "start_ms": round((clock + word.start_s) * 1000),
                "end_ms": round((clock + word.end_s) * 1000),
                "sentence": token.sentence,
                "paragraph": token.paragraph,
                "aligned": word.aligned,
            }
            if token.vocab_sense_id is not None:
                entry["vocabId"] = token.vocab_sense_id
            if token.joined:
                entry["join"] = True
            words.append(entry)
        parts.append(sentence_audio)
        clock += len(sentence_audio) / SAMPLE_RATE

    audio = peak_normalize(concat(parts))
    check_pace(len(words), len(audio) / SAMPLE_RATE)
    return Generated(
        audio=audio,
        words=tuple(words),
        seconds_of_audio=len(audio) / SAMPLE_RATE,
        seconds_to_generate=time.perf_counter() - started,
        characters=characters,
        unaligned_words=sum(1 for w in words if not w["aligned"]),
    )
