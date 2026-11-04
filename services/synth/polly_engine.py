"""Amazon Polly engine (Neural by default) behind the same interface as KokoroEngine.

Polly returns audio and word speech marks in separate calls, so each sentence costs two requests (billed per
character both times). Neural and Long-form voices return word marks; Generative voices do not.
"""
from __future__ import annotations

import json
from typing import Any

import numpy as np

from engine import SAMPLE_RATE, SentenceAudio
from word_mapper import EngineToken

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


class PollyEngine:
    name = "polly"

    def __init__(self, client: Any, voice: str = "Joanna", engine: str = "neural") -> None:
        self._client = client
        self.voice = voice
        self._engine = engine
        self.native_timing = engine != "generative"  # Polly returns no word marks for generative voices; the recognizer supplies the times

    def synthesize(self, sentence: str) -> SentenceAudio:
        audio = self._audio(sentence)
        if audio.size == 0:
            return SentenceAudio(audio, ())
        if not self.native_timing:
            return SentenceAudio(audio, ())
        return SentenceAudio(audio, self._tokens(sentence, len(audio) / SAMPLE_RATE))

    def _request(self, sentence: str, **extra: Any) -> bytes:
        response = self._client.synthesize_speech(
            Text=sentence, VoiceId=self.voice, Engine=self._engine, TextType="text", **extra
        )
        return response["AudioStream"].read()

    def _audio(self, sentence: str) -> np.ndarray:
        raw = self._request(sentence, OutputFormat="pcm", SampleRate=str(POLLY_PCM_RATE))
        pcm = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        if pcm.size == 0:
            return pcm
        target = int(round(len(pcm) * SAMPLE_RATE / POLLY_PCM_RATE))
        return np.interp(np.linspace(0, len(pcm) - 1, target), np.arange(len(pcm)), pcm).astype(np.float32)

    def _tokens(self, sentence: str, duration_s: float) -> tuple[EngineToken, ...]:
        raw = self._request(sentence, OutputFormat="json", SpeechMarkTypes=["word"]).decode("utf-8")
        marks = [m for m in (json.loads(line) for line in raw.splitlines() if line.strip()) if m.get("type") == "word"]
        tokens: list[EngineToken] = []
        for i, mark in enumerate(marks):
            start = mark["time"] / 1000
            end = marks[i + 1]["time"] / 1000 if i + 1 < len(marks) else duration_s
            tokens.append(EngineToken(mark["value"], start, max(end, start)))
        return tuple(tokens)
