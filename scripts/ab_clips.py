"""Build the blind listening test clips.

For each passage that has the AI voice plus another narrator (ReadWorks' human recording, or ReadWorks' current Polly
audio), cut the SAME stretch of text (about 30 s) from every narrator, match their loudness, encode them identically and
save them under random names. The manifest that maps names to narrators is never served to listeners.
"""
from __future__ import annotations

import json
import secrets
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for sub in ("parse", "synth"):
    sys.path.insert(0, str(ROOT / "services" / sub))

from asr_words import decode_audio, transcribe  # noqa: E402
from human_alignment import align_words  # noqa: E402
from mastering import peak_normalize  # noqa: E402
from mp3 import encode_mp3  # noqa: E402

RATE = 24_000
TARGET_SECONDS = 30
PAD_BEFORE_S, PAD_AFTER_S = 0.2, 0.3
TARGET_RMS_DB = -20.0
CLIP_KBPS = 64  # identical for every narrator, so the codec cannot give anything away


def excerpt_range(timing: dict[str, Any]) -> tuple[int, int]:
    """Word index range [0, n) whose AI audio lasts about TARGET_SECONDS."""
    words = timing["words"]
    for i, word in enumerate(words):
        if word["end_ms"] - words[0]["start_ms"] >= TARGET_SECONDS * 1000:
            return 0, i + 1
    return 0, len(words)


def cut(audio: np.ndarray, start_s: float, end_s: float) -> np.ndarray:
    a = max(0, int((start_s - PAD_BEFORE_S) * RATE))
    b = min(len(audio), int((end_s + PAD_AFTER_S) * RATE))
    return audio[a:b]


def speech_rms_db(clip: np.ndarray) -> float:
    """RMS level of the clip's speech: samples above 5% of the clip's own peak, so pauses and room noise do not count
    and a quiet recording is measured as fairly as a loud one."""
    peak = float(np.max(np.abs(clip))) if clip.size else 0.0
    if peak <= 0:
        return -120.0
    active = clip[np.abs(clip) > 0.05 * peak].astype(np.float64)
    return float(20 * np.log10(np.sqrt(np.mean(np.square(active))) + 1e-9))


def match_loudness(clip: np.ndarray) -> np.ndarray:
    """Bring every clip to the same average level (without clipping), so volume cannot bias the rating."""
    gain = 10 ** ((TARGET_RMS_DB - speech_rms_db(clip)) / 20)
    scaled = (clip * gain).astype(np.float32)
    peak = float(np.max(np.abs(scaled))) if scaled.size else 0.0
    return peak_normalize(scaled, -1.0) if peak > 0.89 else scaled


def spans_for(narrator_words: list[dict[str, Any]], first: int, last: int) -> tuple[float, float]:
    return narrator_words[first]["start_ms"] / 1000, narrator_words[last - 1]["end_ms"] / 1000


def build(data_dir: Path, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``sources``: [{passageId, kind: "human"|"polly_current", audioPath, humanId?}] for the non-AI narrators."""
    out = data_dir / "ab"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    manifest: list[dict[str, Any]] = []

    def add(passage_id: str, title: str, kind: str, clip: np.ndarray) -> None:
        token = secrets.token_hex(8)
        (out / f"{token}.mp3").write_bytes(encode_mp3(match_loudness(clip), RATE, CLIP_KBPS))
        manifest.append({"token": token, "passageId": passage_id, "title": title, "kind": kind})

    for src in sources:
        ai = json.loads((data_dir / f"{src['passageId']}.timing.json").read_text())
        first, last = excerpt_range(ai)
        s, e = spans_for(ai["words"], first, last)
        add(ai["id"], ai["title"], "ai", cut(decode_audio(str(data_dir / f"{ai['id']}.mp3"), RATE), s, e))

        if src["kind"] == "human":
            narrator_words = json.loads((data_dir / f"{src['humanId']}.timing.json").read_text())["words"]
        else:  # ReadWorks' current audio has no timing: align it to the text with the recognizer
            heard = transcribe(decode_audio(src["audioPath"], 16_000))
            aligned = align_words([w["text"] for w in ai["words"]], heard)
            narrator_words = [{"start_ms": a.start_s * 1000, "end_ms": a.end_s * 1000} for a in aligned]
        s2, e2 = spans_for(narrator_words, first, last)
        add(ai["id"], ai["title"], src["kind"], cut(decode_audio(src["audioPath"], RATE), s2, e2))

    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    return manifest
