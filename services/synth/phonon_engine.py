"""Phonon text-to-speech: a second, much smaller English engine.

Phonon (gradium/phonon-31m-en, Apache-2.0; runtime `ptts`, MIT or Apache-2.0) is a 31M-parameter model run by a Rust
extension: no PyTorch, no espeak, about 80 MB of files. It gives audio but no word times, so the flow takes word timing
from the recognizer, exactly as it does for Spanish (`native_timing = False`, no tokens).

Only the two voices that won the blind listening test are offered (see services/api/config/VOICES.md). The model has no
speed control: the Settings speed does not apply to these voices (students still change playback speed in the reader).
Pronunciation fixes: plain respellings are spelled into the text; "/phonemes/" entries are Kokoro-only and are skipped.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from typing import Any, Mapping

import numpy as np

from engine import SAMPLE_RATE, SentenceAudio

LOG = logging.getLogger(__name__)

# Our voice id -> the voice's name in Phonon's catalog (gradium/phonon-voices).
PHONON_VOICES = {"phonon_hadley": "Hadley", "phonon_everly": "Everly"}
# The revisions the listening test and benchmarks used. The Docker image bakes exactly these and loads them from disk.
MODEL_REVISION = "8c64b55ec301728e2d1695bfea87a08a267d0c2d"
VOICES_REVISION = "da6c9ec0d47be8df5c87c730a3aa97187f3229c3"
MODEL = f"hf://gradium/phonon-31m-en@{MODEL_REVISION}"
VOICE_CATALOG = f"hf://gradium/phonon-voices@{VOICES_REVISION}"

_TTS: dict[str, Any] = {}
_TTS_LOCK = threading.Lock()


def load_tts() -> Any:
    """Load the model once per process. PHONON_MODEL_DIR and PHONON_VOICES_DIR point at baked local copies (nothing is
    downloaded at run time on Lambda); without them the pinned Hugging Face revisions are fetched and cached."""
    with _TTS_LOCK:
        if "tts" not in _TTS:
            import ptts  # imported lazily so Kokoro-only jobs never need the wheel

            ptts.set_num_threads(int(os.environ.get("PHONON_THREADS", "2")))  # a 4 GB Lambda has about 2 vCPUs
            _TTS["tts"] = ptts.TTS(
                os.environ.get("PHONON_MODEL_DIR") or MODEL,
                lang="en",
                device="cpu",
                voice_catalog=os.environ.get("PHONON_VOICES_DIR") or VOICE_CATALOG,
            )
        return _TTS["tts"]


def apply_respellings(sentence: str, respellings: Mapping[str, str]) -> str:
    """Spell each fixed word as its respelling ("gaieties" -> "gay uh teez"); whole words, any case. "/phonemes/" are skipped."""
    plain = {w.lower(): r for w, r in respellings.items() if not (len(r) > 2 and r.startswith("/") and r.endswith("/"))}
    if not plain:
        return sentence
    pattern = re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(plain, key=len, reverse=True)) + r")\b", re.IGNORECASE)
    return pattern.sub(lambda m: plain[m.group(1).lower()], sentence)


class PhononEngine:
    name = "phonon"
    native_timing = False  # no word times from the model: the recognizer supplies them (see flow.run_flow)

    def __init__(self, voice: str, respellings: Mapping[str, str] | None = None, tts: Any = None) -> None:
        if voice not in PHONON_VOICES:
            raise ValueError(f"Unknown Phonon voice {voice!r}. Use one of: {', '.join(sorted(PHONON_VOICES))}.")
        self.voice = voice
        self._catalog_name = PHONON_VOICES[voice]
        self._respellings = dict(respellings or {})
        self._tts = tts if tts is not None else load_tts()
        if int(self._tts.sample_rate) != SAMPLE_RATE:
            raise ValueError(f"Phonon must produce {SAMPLE_RATE} Hz audio, but the model reports {self._tts.sample_rate} Hz.")

    def synthesize(self, sentence: str) -> SentenceAudio:
        audio = np.asarray(self._tts.synth(apply_respellings(sentence, self._respellings), voice=self._catalog_name), dtype=np.float32)
        if audio.size == 0:
            LOG.warning("engine returned no audio for sentence: %.40s", sentence)
            return SentenceAudio(np.zeros(0, dtype=np.float32), ())
        return SentenceAudio(audio.reshape(-1), ())
