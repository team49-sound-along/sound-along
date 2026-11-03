"""MP3 encoding with lameenc: constant bitrate, mono (VBR seeks inaccurately in browsers).

Delivery bandwidth is ReadWorks' main long-run cost, so the bitrate is a setting (SOUND_ALONG_MP3_KBPS, default 48).
Measured on a generated passage: 32 kbps predicts the same naturalness as 64 kbps at half the file size.
"""
from __future__ import annotations

import os

import numpy as np


def _kbps() -> int:
    raw = os.environ.get("SOUND_ALONG_MP3_KBPS", "48")
    try:
        value = int(raw)
    except ValueError:
        return 48
    return value if 24 <= value <= 128 else 48


BITRATE_KBPS = _kbps()


def encode_mp3(audio: np.ndarray, sample_rate: int) -> bytes:
    import lameenc  # lazy: only needed when actually encoding

    pcm = (np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0) * 32767.0).astype("<i2")
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(BITRATE_KBPS)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_out_sample_rate(sample_rate)
    encoder.set_channels(1)
    encoder.set_quality(2)
    return bytes(encoder.encode(pcm.tobytes()) + encoder.flush())
