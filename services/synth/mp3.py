"""MP3 encoding (constant bitrate, mono). The same encoder runs locally and in the Lambda image.

CBR matters: variable-bitrate MP3 seeks inaccurately in browsers. Bitrate is a stored setting (settings.mp3Kbps);
without one, SOUND_ALONG_MP3_KBPS applies, then 48. Delivery bandwidth is ReadWorks' main long-run cost.
"""
from __future__ import annotations

import os

import numpy as np

MIN_KBPS, MAX_KBPS, DEFAULT_KBPS = 24, 128, 48


def resolve_kbps(requested: object = None) -> int:
    for candidate in (requested, os.environ.get("SOUND_ALONG_MP3_KBPS")):
        try:
            value = int(candidate)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if MIN_KBPS <= value <= MAX_KBPS:
            return value
    return DEFAULT_KBPS


def encode_mp3(audio: np.ndarray, sample_rate: int, kbps: int | None = None) -> bytes:
    import lameenc  # lazy: only needed when actually encoding

    pcm = (np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0) * 32767.0).astype("<i2")
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(resolve_kbps(kbps))
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_out_sample_rate(sample_rate)
    encoder.set_channels(1)
    encoder.set_quality(2)
    return bytes(encoder.encode(pcm.tobytes()) + encoder.flush())
