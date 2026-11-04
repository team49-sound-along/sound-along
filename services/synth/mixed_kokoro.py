"""Splice a sentence from per-language pieces: each foreign span is spoken by the other language's pipeline.

Pieces are level-matched (mastering.level_match) and joined with a short crossfade, so the sentence stays one continuous
clip. Word times: the base language's own tokens are shifted to their place in the sentence; the words of a foreign piece get
tokens WITHOUT times, so the word mapper keeps in step but marks them unaligned instead of guessing (the recognizer pass
replaces all times anyway for engines without native timing).
"""
from __future__ import annotations

from typing import Callable, Sequence

import numpy as np

from engine import SAMPLE_RATE, SentenceAudio
from mastering import level_match
from mixed import ForeignSpan, segments
from word_mapper import EngineToken

CROSSFADE_S = 0.015  # 10-20 ms
Synth = Callable[[str, str], SentenceAudio]  # (language, text) -> audio and tokens


def crossfade_samples(shortest: int) -> int:
    return max(0, min(int(CROSSFADE_S * SAMPLE_RATE), shortest // 2))


def join(parts: Sequence[np.ndarray]) -> tuple[np.ndarray, list[float]]:
    """The parts crossfaded into one clip, and the start second of each part inside it."""
    out = parts[0].astype(np.float32)
    starts = [0.0]
    for part in parts[1:]:
        n = crossfade_samples(min(len(out), len(part)))
        starts.append((len(out) - n) / SAMPLE_RATE)
        if n:
            ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
            blend = out[-n:] * ramp[::-1] + part[:n] * ramp
            out = np.concatenate([out[:-n], blend, part[n:]])
        else:
            out = np.concatenate([out, part])
    return out, starts


def _shift(token: EngineToken, by: float) -> EngineToken:
    return EngineToken(token.text, None if token.start_s is None else token.start_s + by, None if token.end_s is None else token.end_s + by)


def splice_sentence(sentence: str, spans: Sequence[ForeignSpan], base_lang: str, synth: Synth, base_timed: bool) -> SentenceAudio:
    pieces = [(lang, text.strip()) for lang, text in segments(sentence, spans, base_lang) if text.strip()]
    rendered = [(lang, text, synth(lang, text)) for lang, text in pieces]
    rendered = [r for r in rendered if r[2].audio.size]
    if not rendered:
        return SentenceAudio(np.zeros(0, dtype=np.float32), ())
    audio, starts = join(level_match([r[2].audio for r in rendered]))
    tokens: list[EngineToken] = []
    for (lang, text, spoken), start in zip(rendered, starts):
        if lang == base_lang:
            tokens += [_shift(t, start) for t in spoken.tokens]
        else:
            tokens += [EngineToken(word, None, None) for word in text.split()]
    applied = sum(1 for lang, *_ in rendered if lang != base_lang)
    return SentenceAudio(audio, tuple(tokens) if base_timed else (), applied)
