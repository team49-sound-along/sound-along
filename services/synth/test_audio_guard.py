"""Broken narration must fail the job instead of shipping as a silent MP3 (the 2026-11-04 Kokoro-on-Lambda NaN incident)."""
import numpy as np
import pytest

from flow import SilentAudioError, check_audio
from mp3 import encode_mp3


def speech(seconds: float = 0.5) -> np.ndarray:
    return (0.3 * np.sin(np.linspace(0, 2000, int(24_000 * seconds)))).astype(np.float32)


def test_real_audio_passes():
    check_audio(speech())


@pytest.mark.parametrize("audio, message", [
    (np.zeros(0, dtype=np.float32), "no audio"),
    (np.full(24_000, np.nan, dtype=np.float32), "not finite"),
    (np.concatenate([speech(), np.array([np.inf], dtype=np.float32)]), "not finite"),
    (np.zeros(24_000, dtype=np.float32), "silent"),
    (np.full(24_000, 1e-5, dtype=np.float32), "silent"),
])
def test_empty_nan_inf_or_silent_audio_is_refused(audio, message):
    with pytest.raises(SilentAudioError, match=message):
        check_audio(audio, "kokoro")


def test_the_encoder_refuses_nan_instead_of_writing_zeros():
    with pytest.raises(ValueError, match="NaN"):
        encode_mp3(np.full(2400, np.nan, dtype=np.float32), 24_000, 48)
