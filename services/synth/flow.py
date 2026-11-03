"""One passage in, up to two published variants out: the AI voice, and (when a recording is supplied) the human voice.

Pure orchestration with injectable recognition/decoding, so the local CLI and the generator Lambda run identical
code and the tests need no models. Callers do the I/O (files locally, S3 on AWS).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import numpy as np

from artifacts import generate_artifacts
from asr_words import Heard, decode_audio, resample_to_16k, transcribe
from engine import SAMPLE_RATE, Engine
from fingerprint import fingerprint
from human_alignment import align_words
from pipeline import StepCallback, _noop
from review import find_suspects

NARRATOR_LABEL = "ReadWorks narrator"
Transcribe = Callable[..., list[Heard]]
Decode = Callable[[str, int], np.ndarray]


def _recognize(transcribe_fn: Transcribe, audio: np.ndarray, language: str) -> list[Heard]:
    """English keeps the original one-argument call; other languages pass the language so the right model runs."""
    return transcribe_fn(audio) if language == "en" else transcribe_fn(audio, language=language)


def _retime(words: list[dict[str, Any]], heard: list[Heard]) -> list[dict[str, Any]]:
    """Replace word times with the recognizer's, matched to the known text (same method used for human recordings)."""
    aligned = align_words([w["text"] for w in words], heard)
    return [
        {**w, "start_ms": round(a.start_s * 1000), "end_ms": round(a.end_s * 1000), "aligned": a.aligned}
        for w, a in zip(words, aligned)
    ]


@dataclass(frozen=True)
class Variant:
    id: str
    audio: np.ndarray  # float32 mono at SAMPLE_RATE
    timing: dict[str, Any]


@dataclass(frozen=True)
class FlowResult:
    ai: Variant
    human: Optional[Variant]

    @property
    def soundalong(self) -> dict[str, Any]:
        return soundalong_block(self.ai.timing, self.human.timing if self.human else None)


def _voice_entry(kind: str, timing: dict[str, Any]) -> dict[str, Any]:
    # Files are referenced by id, exactly as ReadWorks' own "au" field references audio by filename.
    return {
        "kind": kind, "audio": timing["id"], "timing": f"{timing['id']}.timing.json",
        "engine": timing.get("engine"), "voice": timing.get("voice"), "durationMs": timing.get("duration_ms"),
    }


def soundalong_block(ai_timing: dict[str, Any], human_timing: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """The one document ReadWorks' frontend needs per passage: both voices, the default, and feature flags.

    It is meant to be merged into the passage's existing product JSON (see docs/FORMAT.md)."""
    voices = ([_voice_entry("human", human_timing)] if human_timing else []) + [_voice_entry("ai", ai_timing)]
    return {
        "soundAlong": {"version": 1, "passageId": ai_timing["id"], "defaultVoice": voices[0]["kind"], "voices": voices},
        "features": ["sa"] + (["sahv"] if human_timing else []),
    }


def _human_variant(ai_timing: dict[str, Any], passage: dict[str, Any], recording_path: str,
                   transcribe_fn: Transcribe, decode_fn: Decode, language: str) -> Variant:
    heard = _recognize(transcribe_fn, decode_fn(recording_path, 16_000), language)
    audio = decode_fn(recording_path, SAMPLE_RATE)
    words = _retime(ai_timing["words"], heard)
    seconds = len(audio) / SAMPLE_RATE
    unaligned = sum(1 for w in words if not w["aligned"])
    metrics = {
        "characters": sum(len(w["text"]) + 1 for w in words), "words": len(words), "audioSeconds": round(seconds, 2),
        "generateSeconds": 0, "realTimeFactor": 0, "unalignedWords": unaligned,
        "pollyNeuralUsd": 0, "pollyStandardUsd": 0, "estimatedLambdaUsd": 0,
        "estimateBasis": "Existing human recording: alignment only, no speech synthesis",
    }
    human_id = passage["humanPassageId"]
    timing = {
        "id": human_id, "title": ai_timing.get("title"), "engine": "human", "voice": NARRATOR_LABEL,
        "pairId": ai_timing["id"], "language": language, "duration_ms": round(seconds * 1000), "metrics": metrics,
        "vocab": ai_timing.get("vocab", {}), "words": words,
        **({"generatedWith": ai_timing["generatedWith"]} if "generatedWith" in ai_timing else {}),
    }
    return Variant(human_id, audio, timing)


def run_flow(
    passage: dict[str, Any],
    engine: Engine,
    on_step: StepCallback = _noop,
    recording_path: Optional[str] = None,
    transcribe_fn: Transcribe = transcribe,
    decode_fn: Decode = decode_audio,
) -> FlowResult:
    """``passage`` is the job input file: uuid, title, content, and optionally settings, pronunciations,
    humanPassageId and qualityCheck."""
    if recording_path and not passage.get("humanPassageId"):
        raise ValueError("A recording needs a humanPassageId so the two variants can be linked.")

    language = passage.get("language") or "en"
    artifacts = generate_artifacts(passage, engine, on_step)
    timing = {
        **artifacts.timing, "language": language,
        "generatedWith": {
            "settings": passage.get("settings"), "pronunciations": passage.get("pronunciations"),
            "hash": fingerprint(passage, recording_path),
        },
    }

    heard_ai: Optional[list[Heard]] = None
    if not getattr(engine, "native_timing", True):
        # The engine (Kokoro in Spanish) gives audio but no word times: take them from a recognizer pass instead.
        heard_ai = _recognize(transcribe_fn, resample_to_16k(artifacts.audio, SAMPLE_RATE), language)
        words = _retime(timing["words"], heard_ai)
        timing = {**timing, "words": words, "metrics": {**timing["metrics"], "unalignedWords": sum(1 for w in words if not w["aligned"])}}

    if passage.get("qualityCheck"):
        if heard_ai is None:
            heard_ai = _recognize(transcribe_fn, resample_to_16k(artifacts.audio, SAMPLE_RATE), language)
        suspects = find_suspects([w["text"] for w in timing["words"]], heard_ai)
        timing = {**timing, "review": {"source": "asr-check", "suspects": suspects}}

    human = None
    if recording_path:
        human = _human_variant(timing, passage, recording_path, transcribe_fn, decode_fn, language)
        timing = {**timing, "pairId": human.id}
    return FlowResult(ai=Variant(passage["uuid"], artifacts.audio, timing), human=human)
