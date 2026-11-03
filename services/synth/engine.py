"""Pluggable TTS engine interface and the Kokoro implementation.

An engine turns a list of sentences into one audio track plus per-sentence word tokens.
Polly (speech marks) and others implement the same Protocol later.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

import numpy as np

from pronunciations import apply_overrides, build_phonemes, load_respellings
from word_mapper import EngineToken

LOG = logging.getLogger(__name__)
SAMPLE_RATE = 24_000


@dataclass(frozen=True)
class SentenceAudio:
    audio: np.ndarray  # float32 mono at SAMPLE_RATE
    tokens: tuple[EngineToken, ...]  # times are seconds from the start of THIS sentence's audio


class Engine(Protocol):
    name: str
    voice: str

    def synthesize(self, sentence: str) -> SentenceAudio: ...


_PIPELINE: Any = None
_PIPELINE_LOCK = threading.Lock()


def _shared_pipeline() -> Any:
    """Load the model once per process (about 4 s); every job after that creates its engine instantly."""
    global _PIPELINE
    with _PIPELINE_LOCK:
        if _PIPELINE is None:
            from kokoro import KPipeline  # imported lazily so Lambda init stays small

            _PIPELINE = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
        return _PIPELINE


class KokoroEngine:
    """Kokoro-82M (Apache-2.0) via the PyTorch ``kokoro`` package; English only for word timestamps.

    Voice, speed and pronunciation fixes are per-job settings: they come from the job's input file, not from code.
    """

    name = "kokoro"

    def __init__(self, voice: str = "af_heart", speed: float = 0.95, respellings: Mapping[str, str] | None = None) -> None:
        self._pipeline = _shared_pipeline()
        self.voice = voice
        self._speed = speed
        chosen = load_respellings() if respellings is None else respellings
        self._phonemes = build_phonemes(chosen, lambda text: self._pipeline.g2p(text)[0])

    def synthesize(self, sentence: str) -> SentenceAudio:
        chunks: list[np.ndarray] = []
        tokens: list[EngineToken] = []
        offset = 0.0
        spoken_text = apply_overrides(sentence, self._phonemes)
        for result in self._pipeline(spoken_text, voice=self.voice, speed=self._speed):
            if result.audio is None:
                continue
            audio = np.asarray(result.audio, dtype=np.float32)
            for token in result.tokens or []:
                start = None if token.start_ts is None else token.start_ts + offset
                end = None if token.end_ts is None else token.end_ts + offset
                tokens.append(EngineToken(token.text, start, end))
            chunks.append(audio)
            offset += len(audio) / SAMPLE_RATE
        if not chunks:
            LOG.warning("engine returned no audio for sentence: %.40s", sentence)
            return SentenceAudio(np.zeros(0, dtype=np.float32), ())
        return SentenceAudio(np.concatenate(chunks), tuple(tokens))


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)


def concat(parts: Sequence[np.ndarray]) -> np.ndarray:
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
