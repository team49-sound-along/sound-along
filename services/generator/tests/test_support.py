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


def test_encode_mp3_is_cbr_mono_at_the_requested_bitrate():
    pytest.importorskip("lameenc")
    from mp3 import encode_mp3

    audio = (0.2 * np.sin(np.linspace(0, 2000, 24000 * 2))).astype(np.float32)
    for kbps in (32, 64):
        data = encode_mp3(audio, 24000, kbps)
        assert data[:3] == b"ID3" or data[0] == 0xFF
        expected = 2 * kbps * 1000 / 8  # about 2 s of audio
        assert expected * 0.9 < len(data) < expected * 1.1


def test_bitrate_resolution_prefers_the_setting_then_the_environment_then_the_default(monkeypatch):
    from mp3 import resolve_kbps

    monkeypatch.delenv("SOUND_ALONG_MP3_KBPS", raising=False)
    assert resolve_kbps(32) == 32 and resolve_kbps(None) == 48 and resolve_kbps(999) == 48 and resolve_kbps("x") == 48
    monkeypatch.setenv("SOUND_ALONG_MP3_KBPS", "64")
    assert resolve_kbps(None) == 64 and resolve_kbps(24) == 24


def test_vocab_count_counts_distinct_words_not_senses():
    """Twin of the JS rule in services/api/src/passageSummary.js: 'tax' (noun) and 'tax' (verb) are two senses but one word."""
    from summary import passage_summary

    timing = {"id": "x", "vocab": {"4217601": {"word": "tax"}, "4217603": {"word": "Tax"}, "813901": {"word": "colonist"},
                                    "1179703": {"word": "disguise"}, "3277401": {"word": "principle"}}}
    assert passage_summary(timing, "2026-11-03T00:00:00Z")["vocabCount"] == 4
    assert passage_summary({"id": "x"}, "t")["vocabCount"] == 0
    assert passage_summary({"id": "x", "vocab": {"1": {"word": "nature"}, "2": {"definition": "no word"}, "3": {"word": "  "}}}, "t")["vocabCount"] == 1


def test_summaries_and_index_entries_carry_the_translation_links():
    from summary import index_entry, passage_summary

    s = passage_summary({"id": "x", "translations": {"es": {"id": "T1", "sentenceMap": [[0]]}, "fr": {}}}, "t")
    assert s["translations"] == {"es": "T1"} and s["translationOf"] is None
    back = passage_summary({"id": "T1", "language": "es", "translationOf": {"id": "x", "lang": "en", "sentenceMap": [0]}}, "t")
    assert back["translationOf"] == "x" and back["translations"] == {}
    assert index_entry(s)["translations"] == {"es": "T1"} and index_entry({"id": "a"})["translations"] == {} and index_entry({"id": "a"})["translationOf"] is None
