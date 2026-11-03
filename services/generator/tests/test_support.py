import numpy as np
import pytest

from dynamo import to_dynamo
from summary import passage_summary


def test_to_dynamo_converts_nested_floats():
    out = to_dynamo({"a": 1.5, "b": [2.25, {"c": 3}], "d": None, "e": True})
    assert str(out["a"]) == "1.5" and str(out["b"][0]) == "2.25"
    assert out["b"][1]["c"] == 3 and out["d"] is None and out["e"] is True


def test_to_dynamo_rejects_unsupported_types():
    with pytest.raises(TypeError):
        to_dynamo({"a": object()})


def test_summary_defaults_like_catalog_js():
    s = passage_summary({"id": "i"}, "2026-01-01T00:00:00.000Z")
    assert (s["title"], s["words"], s["durationMs"], s["engine"], s["voice"], s["vocabCount"]) == ("Untitled passage", 0, 0, "unknown", "unknown", 0)


def test_encode_mp3_is_cbr_mono_at_the_configured_bitrate():
    pytest.importorskip("lameenc")
    from audio import BITRATE_KBPS, encode_mp3

    audio = (0.2 * np.sin(np.linspace(0, 2000, 24000 * 2))).astype(np.float32)
    data = encode_mp3(audio, 24000)
    assert data[:3] == b"ID3" or data[0] == 0xFF
    expected = 2 * BITRATE_KBPS * 1000 / 8  # about 2 s of audio
    assert expected * 0.9 < len(data) < expected * 1.1
