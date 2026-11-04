"""Pluggable TTS engine interface and the Kokoro implementation.

An engine turns a list of sentences into one audio track plus per-sentence word tokens.
Polly (speech marks) and others implement the same Protocol later.
"""
from __future__ import annotations

import logging
import os
import re
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


LANGUAGES = {"en": "a", "es": "e"}  # Kokoro language codes: American English, Spanish
DEFAULT_VOICE = {"en": "af_heart", "es": "ef_dora"}
_PIPELINES: dict[str, Any] = {}
_PIPELINE_LOCK = threading.Lock()


_TORCH_CONFIGURED = False


def configure_torch() -> None:
    """Make PyTorch safe on Graviton Lambda before any model runs.

    In the Lambda sandbox /sys/devices/system/cpu is unreadable, so PyTorch's cpuinfo cannot detect the CPU and NNPACK fails to initialize
    ("Could not initialize NNPACK! Reason: Out of memory"). On 2026-11-04 a Kokoro job in that state produced NaN audio. NNPACK is switched
    off (convolutions fall back to the default kernels) and the thread count is fixed instead of guessed from the unreadable CPU list.
    TORCH_NNPACK=1 turns NNPACK back on; TORCH_THREADS sets the threads (default 2, a 4 GB Lambda has about 2 vCPUs)."""
    global _TORCH_CONFIGURED
    if _TORCH_CONFIGURED:
        return
    import torch

    if os.environ.get("TORCH_NNPACK") != "1":
        try:
            torch.backends.nnpack.set_flags(False)
        except Exception:  # noqa: BLE001 (older or newer builds without the switch: nothing to turn off)
            LOG.info("NNPACK switch not available in this PyTorch build")
    threads = int(os.environ.get("TORCH_THREADS") or 2)
    torch.set_num_threads(threads)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:  # can only be set once per process, before parallel work starts
        pass
    _TORCH_CONFIGURED = True


def _shared_pipeline(language: str = "en") -> Any:
    """Load each language's pipeline once per process (about 4 s); every job after that creates its engine instantly."""
    with _PIPELINE_LOCK:
        if language not in _PIPELINES:
            configure_torch()
            from kokoro import KPipeline  # imported lazily so Lambda init stays small

            _PIPELINES[language] = KPipeline(lang_code=LANGUAGES[language], repo_id="hexgrad/Kokoro-82M")
        return _PIPELINES[language]


SPANISH_MAX_WORDS = 40  # Kokoro drops everything after about 510 phonemes of a non-English text; 40 Spanish words stay well under that
PIECE_GAP_S = 0.12  # a short breath where a long sentence was cut at a comma or semicolon


def split_for_tts(text: str, max_words: int = SPANISH_MAX_WORDS) -> list[str]:
    """Pieces of at most `max_words` words, cut after commas, semicolons, colons and dashes where possible, otherwise by words."""
    clauses = [c for c in re.split(r"(?<=[,;:—–])\s+", text.strip()) if c.strip()]
    pieces: list[str] = []
    current: list[str] = []
    for clause in clauses:
        words = clause.split()
        if current and len(current) + len(words) > max_words:
            pieces.append(" ".join(current))
            current = []
        while len(words) > max_words:
            pieces.append(" ".join(words[:max_words]))
            words = words[max_words:]
        current += words
    if current:
        pieces.append(" ".join(current))
    return pieces or [text]


class KokoroEngine:
    """Kokoro-82M (Apache-2.0) via the PyTorch ``kokoro`` package; English only for word timestamps.

    Voice, speed and pronunciation fixes are per-job settings: they come from the job's input file, not from code.
    """

    name = "kokoro"

    def __init__(
        self,
        voice: str | None = None,
        speed: float = 0.95,
        respellings: Mapping[str, str] | None = None,
        language: str = "en",
    ) -> None:
        if language not in LANGUAGES:
            raise ValueError(f"Unsupported language {language!r}. Use 'en' or 'es'.")
        self.language = language
        # Kokoro returns word timestamps for English only; for Spanish the flow gets them from a recognizer instead.
        self.native_timing = language == "en"
        self._pipeline = _shared_pipeline(language)
        self.voice = voice or DEFAULT_VOICE[language]
        self._speed = speed
        # Pronunciation fixes are respellings run through the ENGLISH grapheme-to-phoneme step, so English only.
        chosen = {} if language != "en" else (load_respellings() if respellings is None else respellings)
        self._phonemes = build_phonemes(chosen, lambda text: self._pipeline.g2p(text)[0])

    def synthesize(self, sentence: str) -> SentenceAudio:
        chunks: list[np.ndarray] = []
        tokens: list[EngineToken] = []
        offset = 0.0
        spoken_text = apply_overrides(sentence, self._phonemes)
        pieces = [spoken_text] if self.language == "en" else split_for_tts(spoken_text)  # English: Kokoro splits by tokens itself
        for n, piece in enumerate(pieces):
            if n and piece_gap(pieces[n - 1]):
                chunks.append(silence(PIECE_GAP_S))
                offset += PIECE_GAP_S
            for result in self._pipeline(piece, voice=self.voice, speed=self._speed):
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


def piece_gap(previous: str) -> bool:
    return previous.rstrip()[-1:] in ",;:—–"


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)


def concat(parts: Sequence[np.ndarray]) -> np.ndarray:
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
