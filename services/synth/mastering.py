"""Light, deterministic audio mastering applied to every generated passage.

Per-sentence synthesis can leave neighbouring sentences at slightly different loudness and with hard edges
(audible clicks). These helpers even out loudness, soften edges and set a safe peak. They change gain and
the first/last few milliseconds only, so word timing is unaffected. Pure numpy, no ffmpeg.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

SAMPLE_RATE = 24_000
_FLOOR = 1e-9
_ACTIVE = 0.01  # samples quieter than this count as pauses when measuring loudness


def rms_db(audio: np.ndarray) -> float:
    """Loudness of the speech part of ``audio`` in dB (RMS of non-silent samples)."""
    active = audio[np.abs(audio) > _ACTIVE]
    if active.size == 0:
        return -120.0
    return float(20 * np.log10(np.sqrt(np.mean(np.square(active, dtype=np.float64))) + _FLOOR))


def level_match(audios: Sequence[np.ndarray], max_adjust_db: float = 3.0) -> list[np.ndarray]:
    """Move each audio toward the median loudness, by at most ``max_adjust_db`` either way."""
    levels = [rms_db(a) for a in audios]
    speech_levels = [lv for lv in levels if lv > -100]
    if not speech_levels:
        return [a.copy() for a in audios]
    target = float(np.median(speech_levels))
    matched: list[np.ndarray] = []
    for audio, level in zip(audios, levels):
        if level <= -100:
            matched.append(audio.copy())
            continue
        gain_db = float(np.clip(target - level, -max_adjust_db, max_adjust_db))
        matched.append((audio * (10 ** (gain_db / 20))).astype(np.float32))
    return matched


def fade_edges(audio: np.ndarray, ms: float = 8.0, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Short fade in and out so concatenated sentences never click."""
    n = min(int(sample_rate * ms / 1000), len(audio) // 2)
    if n <= 0:
        return audio.copy()
    out = audio.copy()
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    out[:n] *= ramp
    out[-n:] *= ramp[::-1]
    return out


def peak_normalize(audio: np.ndarray, peak_db: float = -1.0) -> np.ndarray:
    """Scale so the loudest sample sits at ``peak_db`` dBFS (headroom against clipping after MP3 encoding)."""
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak < _FLOOR:
        return audio.copy()
    return (audio * (10 ** (peak_db / 20) / peak)).astype(np.float32)
