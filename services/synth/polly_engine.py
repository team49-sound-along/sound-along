"""Amazon Polly engine (Neural by default) behind the same interface as KokoroEngine.

Polly returns audio and word speech marks in separate calls, so each sentence costs two requests (billed per
character both times). Neural and Long-form voices return word marks; Generative voices do not.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Sequence

import numpy as np

from engine import SAMPLE_RATE, SentenceAudio
from mixed import ForeignSpan
from ssml import SsmlDoc, build_ssml, word_marks
from word_mapper import EngineToken

LOG = logging.getLogger(__name__)

POLLY_PCM_RATE = 16_000  # the highest PCM rate Polly offers for neural voices

# Engines each voice can use (AWS docs: Neural, Generative and Long-form voices pages). Word speech marks exist for neural and long-form voices only;
# for a generative voice the audio comes from Polly and the word times from the recognizer (flow.run_flow), exactly as for Kokoro in Spanish.
POLLY_VOICES: dict[str, dict[str, Any]] = {
    "Joanna": {"lang": "en-US", "engines": ("neural", "generative", "long-form")},
    "Matthew": {"lang": "en-US", "engines": ("neural", "generative", "long-form")},
    "Ruth": {"lang": "en-US", "engines": ("neural", "generative", "long-form")},
    "Lupe": {"lang": "es-US", "engines": ("neural", "generative")},
    "Pedro": {"lang": "es-US", "engines": ("neural",)},
    "Carlos": {"lang": "es-US", "engines": ("generative",)},
    "Mia": {"lang": "es-MX", "engines": ("neural", "generative")},
    "Andrés": {"lang": "es-MX", "engines": ("neural", "generative")},
    "Lucia": {"lang": "es-ES", "engines": ("neural", "generative")},
    "Sergio": {"lang": "es-ES", "engines": ("neural", "generative")},
    "Alba": {"lang": "es-ES", "engines": ("long-form",)},
    "Raúl": {"lang": "es-ES", "engines": ("long-form",)},
}
ENGINES = ("neural", "generative", "long-form", "standard")


def polly_voice_for(language: str, env: Any) -> tuple[str, str]:
    """(voice, engine) from POLLY_VOICE / POLLY_VOICE_ES and POLLY_ENGINE. A voice that cannot use the chosen engine is refused here, before any request is billed."""
    voice = (env.get("POLLY_VOICE") or "Joanna") if language == "en" else (env.get("POLLY_VOICE_ES") or "Lupe")
    engine = (env.get("POLLY_ENGINE") or "neural").lower()
    if engine not in ENGINES:
        raise ValueError(f"Unknown POLLY_ENGINE {engine!r}. Use one of {', '.join(ENGINES)}.")
    known = POLLY_VOICES.get(voice)
    if known and engine != "standard" and engine not in known["engines"]:
        raise ValueError(f"Polly voice {voice} cannot use the {engine} engine (it supports {', '.join(known['engines'])}).")
    return voice, engine


def _is_invalid_ssml(exc: Exception) -> bool:
    code = (getattr(exc, "response", None) or {}).get("Error", {}).get("Code", "")
    return "InvalidSsml" in str(code) or "InvalidSsml" in type(exc).__name__


class PollyEngine:
    name = "polly"

    def __init__(self, client: Any, voice: str = "Joanna", engine: str = "neural") -> None:
        self._client = client
        self.voice = voice
        self._engine = engine
        self.native_timing = engine != "generative"  # Polly returns no word marks for generative voices; the recognizer supplies the times
        self.accepts_spans = engine != "long-form"  # <lang> is verified for neural, generative and standard only

    def synthesize(self, sentence: str, spans: Sequence[ForeignSpan] = ()) -> SentenceAudio:
        """With ``spans`` the foreign words are wrapped in SSML <lang> tags. Polly refusing the SSML costs nothing but the tags: the sentence is read plain."""
        if spans and self.accepts_spans:
            doc = build_ssml(sentence, spans)
            try:
                return self._speak(doc.ssml, doc, len(spans))
            except Exception as exc:  # noqa: BLE001
                if not _is_invalid_ssml(exc):
                    raise
                LOG.warning("Polly rejected the SSML for a sentence; retrying without language tags: %.60s", sentence)
        return self._speak(sentence, None, 0)

    def _speak(self, text: str, doc: SsmlDoc | None, applied: int) -> SentenceAudio:
        audio = self._audio(text, doc)
        if audio.size == 0 or not self.native_timing:
            return SentenceAudio(audio, (), applied if audio.size else 0)
        return SentenceAudio(audio, self._tokens(text, doc, len(audio) / SAMPLE_RATE), applied)

    def _request(self, text: str, doc: SsmlDoc | None, **extra: Any) -> bytes:
        response = self._client.synthesize_speech(
            Text=text, VoiceId=self.voice, Engine=self._engine, TextType="text" if doc is None else "ssml", **extra
        )
        return response["AudioStream"].read()

    def _audio(self, text: str, doc: SsmlDoc | None = None) -> np.ndarray:
        raw = self._request(text, doc, OutputFormat="pcm", SampleRate=str(POLLY_PCM_RATE))
        pcm = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        if pcm.size == 0:
            return pcm
        target = int(round(len(pcm) * SAMPLE_RATE / POLLY_PCM_RATE))
        return np.interp(np.linspace(0, len(pcm) - 1, target), np.arange(len(pcm)), pcm).astype(np.float32)

    def _tokens(self, text: str, doc: SsmlDoc | None, duration_s: float) -> tuple[EngineToken, ...]:
        raw = self._request(text, doc, OutputFormat="json", SpeechMarkTypes=["word"]).decode("utf-8")
        parsed = (json.loads(line) for line in raw.splitlines() if line.strip())
        marks = word_marks(list(parsed), doc)
        tokens: list[EngineToken] = []
        for i, mark in enumerate(marks):
            start = mark["time"] / 1000
            end = marks[i + 1]["time"] / 1000 if i + 1 < len(marks) else duration_s
            tokens.append(EngineToken(mark["value"], start, max(end, start)))
        return tuple(tokens)
