"""Amazon Polly engine (Neural by default) behind the same interface as KokoroEngine.

Polly returns audio and word speech marks in separate calls, so each sentence costs two requests (billed per
character both times). Neural and Long-form voices return word marks; Generative voices do not.
"""
from __future__ import annotations

import json
import logging
import unicodedata
from typing import Any, Mapping, Sequence

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
    "Danielle": {"lang": "en-US", "engines": ("neural", "generative", "long-form")},
    "Salli": {"lang": "en-US", "engines": ("neural", "generative")},
    "Kendra": {"lang": "en-US", "engines": ("neural",)},
    "Kimberly": {"lang": "en-US", "engines": ("neural",)},
    "Stephen": {"lang": "en-US", "engines": ("neural", "generative")},
    "Gregory": {"lang": "en-US", "engines": ("neural", "long-form")},
    "Joey": {"lang": "en-US", "engines": ("neural",)},
    "Ivy": {"lang": "en-US", "engines": ("neural",)},
    "Kevin": {"lang": "en-US", "engines": ("neural",)},
    "Justin": {"lang": "en-US", "engines": ("neural",)},
    "Matthew": {"lang": "en-US", "engines": ("neural", "generative", "long-form")},
    "Ruth": {"lang": "en-US", "engines": ("neural", "generative", "long-form")},
    "Lupe": {"lang": "es-US", "engines": ("neural", "generative")},
    "Pedro": {"lang": "es-US", "engines": ("neural",)},
    "Carlos": {"lang": "es-US", "engines": ("generative",)},
    "Mia": {"lang": "es-MX", "engines": ("neural", "generative")},
    "Andres": {"lang": "es-MX", "engines": ("neural", "generative")},
    "Lucia": {"lang": "es-ES", "engines": ("neural", "generative")},
    "Sergio": {"lang": "es-ES", "engines": ("neural", "generative")},
    "Alba": {"lang": "es-ES", "engines": ("long-form",)},
    "Raul": {"lang": "es-ES", "engines": ("long-form",)},
}
ENGINES = ("neural", "generative", "long-form", "standard")


def canonical_voice(voice: str) -> str:
    """The ASCII VoiceId: Polly's accented display names (Andrés, Raúl) and their ASCII ids are the same voice."""
    return "".join(c for c in unicodedata.normalize("NFD", voice) if unicodedata.category(c) != "Mn")


def _job_voice(language: str, options: Mapping[str, Any]) -> str | None:
    """The voice the teacher chose for this language, when it is a Polly voice that speaks it (an open-source id saved earlier is ignored)."""
    chosen = options.get("voice" if language == "en" else "voiceEs")
    known = POLLY_VOICES.get(canonical_voice(chosen)) if isinstance(chosen, str) else None
    return canonical_voice(chosen) if known and known["lang"].startswith(language) else None


def _degrade(engine: str, supported: Sequence[str]) -> str:
    """The asked-for quality when the voice has it, else the voice's neural or generative one: a teacher's choice never fails a job."""
    if engine == "standard" or engine in supported:
        return engine
    return next((e for e in ("neural", "generative") if e in supported), supported[0])


def polly_choice(language: str, options: Mapping[str, Any], env: Any) -> tuple[str, str]:
    """(voice, engine) for one job. The job's own choice (options voice/voiceEs and pollyEngine, from Settings) wins; otherwise POLLY_VOICE /
    POLLY_VOICE_ES and POLLY_ENGINE apply, then Joanna / Lupe and neural. With only deployment settings, a voice that cannot use the engine is
    refused here, before any request is billed; with a teacher's choice the voice's own best quality is used instead."""
    default = (env.get("POLLY_VOICE") or "Joanna") if language == "en" else (env.get("POLLY_VOICE_ES") or "Lupe")
    job_voice = _job_voice(language, options)
    voice = job_voice or default
    asked = options.get("pollyEngine")
    engine = str(asked or env.get("POLLY_ENGINE") or "neural").lower()
    if engine not in ENGINES:
        raise ValueError(f"Unknown {'pollyEngine' if asked else 'POLLY_ENGINE'} {engine!r}. Use one of {', '.join(ENGINES)}.")
    known = POLLY_VOICES.get(canonical_voice(voice))
    if known and engine != "standard" and engine not in known["engines"]:
        if not (job_voice or asked):
            raise ValueError(f"Polly voice {voice} cannot use the {engine} engine (it supports {', '.join(known['engines'])}).")
        engine = _degrade(engine, known["engines"])
    return canonical_voice(voice) if known else voice, engine


def polly_voice_for(language: str, env: Any) -> tuple[str, str]:
    """(voice, engine) from the deployment's POLLY_VOICE / POLLY_VOICE_ES and POLLY_ENGINE alone."""
    return polly_choice(language, {}, env)


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
