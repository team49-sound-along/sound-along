"""Build the timing document and metrics for one passage (no I/O, no encoding).

Shared by the local CLI (run_local.py) and the AWS generator Lambda.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np

from engine import Engine
from mixed import passage_enabled
from phrases import phrase_ends
from pipeline import Generated, StepCallback, _noop, generate

# Pricing used for the cost comparison. Polly rates are from the AWS Polly pricing page (per 1M characters);
# Lambda is the us-west-2 x86 rate per GB-second. Lambda compute is an ESTIMATE, see lambda_estimate().
POLLY_NEURAL_PER_M = 16.0
POLLY_STANDARD_PER_M = 4.0
LAMBDA_PER_GB_SECOND = 0.0000166667
LAMBDA_MEMORY_GB = 4.0
LAMBDA_SLOWDOWN_VS_LOCAL = 5.0  # assumption: a 4 GB Lambda is ~5x slower than this machine; replace with a measurement


@dataclass(frozen=True)
class Artifacts:
    audio: np.ndarray  # float32 mono at engine.SAMPLE_RATE
    timing: dict[str, Any]  # the full timing document (docs/API.md)
    metrics: dict[str, Any]  # same object as timing["metrics"]


def lambda_estimate(seconds_to_generate: float) -> float:
    return seconds_to_generate * LAMBDA_SLOWDOWN_VS_LOCAL * LAMBDA_MEMORY_GB * LAMBDA_PER_GB_SECOND


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def vocab_from_words(passage: dict[str, Any], words: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Annotation data for every vocab word that appears in ``words``: definition, part of speech,
    example sentences and Spanish translations, all taken from the passage's own vocabulary data."""
    senses = (passage.get("vocab") or {}).get("support", {}).get("senses", {})
    used = {w["vocabId"] for w in words if "vocabId" in w}
    notes: dict[str, dict[str, Any]] = {}
    for sid in sorted(used):
        sense = senses.get(sid)
        if not sense:
            continue
        note: dict[str, Any] = {"word": sense.get("word"), "definition": _clean(sense.get("definition"))}
        if sense.get("part_of_speech"):
            note["partOfSpeech"] = _clean(sense["part_of_speech"][0])
        examples = [_clean(e) for e in (sense.get("example_list") or []) if _clean(e)][:2]
        if examples:
            note["examples"] = examples
        spanish = [_clean(e) for e in (sense.get("spanish") or []) if _clean(e)][:3]
        if spanish:
            note["spanish"] = spanish
        notes[sid] = note
    return notes


def vocab_for(passage: dict[str, Any], result: Generated) -> dict[str, dict[str, Any]]:
    return vocab_from_words(passage, result.words)


def build_metrics(result: Generated) -> dict[str, Any]:
    return {
        "characters": result.characters,
        "words": len(result.words),
        "audioSeconds": round(result.seconds_of_audio, 2),
        "generateSeconds": round(result.seconds_to_generate, 2),
        "realTimeFactor": round(result.seconds_to_generate / max(result.seconds_of_audio, 0.001), 3),
        "unalignedWords": result.unaligned_words,
        "foreignSpans": result.foreign_spans,
        "pollyNeuralUsd": round(result.characters / 1e6 * POLLY_NEURAL_PER_M, 4),
        "pollyStandardUsd": round(result.characters / 1e6 * POLLY_STANDARD_PER_M, 4),
        "estimatedLambdaUsd": round(lambda_estimate(result.seconds_to_generate), 4),
        "estimateBasis": f"Lambda {LAMBDA_MEMORY_GB:g} GB, assumed {LAMBDA_SLOWDOWN_VS_LOCAL:g}x slower than the generating machine",
    }


def build_timing(passage: dict[str, Any], engine: Engine, result: Generated, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": passage["uuid"],
        "title": passage.get("title"),
        "engine": engine.name,
        "voice": engine.voice,
        "duration_ms": round(result.seconds_of_audio * 1000),
        "metrics": metrics,
        "vocab": vocab_for(passage, result),
        "words": phrase_ends(result.words),
    }


def generate_artifacts(passage: dict[str, Any], engine: Engine, on_step: StepCallback = _noop) -> Artifacts:
    """Run parse -> synthesize -> align. The caller encodes the audio and publishes (the "publish" step)."""
    result = generate(passage["content"], engine, on_step, language=passage.get("language") or "en", mixed_language=passage_enabled(passage))
    metrics = build_metrics(result)
    return Artifacts(audio=result.audio, timing=build_timing(passage, engine, result, metrics), metrics=metrics)
