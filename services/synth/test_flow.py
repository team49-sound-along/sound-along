import numpy as np

from asr_words import Heard
from engine import SAMPLE_RATE, SentenceAudio
from flow import run_flow
from word_mapper import EngineToken

HTML = "<p>Hello world. We saw gaieties today.</p>"


class FakeEngine:
    name = "fake"
    voice = "fake_voice"

    def synthesize(self, sentence: str) -> SentenceAudio:
        words = sentence.split()
        tokens = tuple(EngineToken(w.strip(".,"), i * 0.4, i * 0.4 + 0.3) for i, w in enumerate(words))
        return SentenceAudio(np.full(int(0.4 * len(words) * SAMPLE_RATE), 0.1, dtype=np.float32), tokens)


def heard(words, shift=0.0):
    return [Heard(w, i * 0.5 + shift, i * 0.5 + shift + 0.4) for i, w in enumerate(words)]


PASSAGE = {"uuid": "ai-1", "title": "T", "content": HTML, "humanPassageId": "hu-1",
           "settings": {"voice": "af_bella"}, "pronunciations": {"gaieties": "gayetees"}}


def test_ai_only_flow_has_no_human_variant_and_no_review_unless_asked():
    out = run_flow({k: v for k, v in PASSAGE.items() if k != "humanPassageId"}, FakeEngine())
    assert out.human is None and "review" not in out.ai.timing and "pairId" not in out.ai.timing
    assert out.ai.id == "ai-1" and len(out.ai.timing["words"]) == 6


def test_quality_check_records_only_clearly_different_words_as_suspects():
    spoken = heard(["hello", "world", "we", "saw", "deities", "today"])
    out = run_flow({**PASSAGE, "qualityCheck": True}, FakeEngine(), transcribe_fn=lambda audio: spoken)
    assert out.ai.timing["review"] == {"source": "asr-check", "suspects": [{"expected": "gaieties", "heard": "deities"}]}


def test_recording_produces_a_linked_human_variant_with_the_same_words(tmp_path):
    rec = tmp_path / "rec.mp3"
    rec.write_bytes(b"audio")
    recording = np.zeros(24000 * 5, dtype=np.float32)
    spoken = heard(["hello", "world", "we", "saw", "gaieties", "today"], shift=1.0)
    out = run_flow(PASSAGE, FakeEngine(), recording_path=str(rec),
                   transcribe_fn=lambda audio: spoken, decode_fn=lambda path, rate: recording)
    ai, human = out.ai, out.human
    assert human is not None and human.id == "hu-1"
    assert ai.timing["pairId"] == "hu-1" and human.timing["pairId"] == "ai-1"
    assert human.timing["engine"] == "human"
    assert [w["text"] for w in human.timing["words"]] == [w["text"] for w in ai.timing["words"]]
    assert human.timing["words"][0]["start_ms"] == 1000 and human.timing["words"][0]["aligned"] is True
    assert human.timing["duration_ms"] == 5000 and human.timing["metrics"]["unalignedWords"] == 0


def test_generated_with_records_the_settings_and_pronunciations_used():
    out = run_flow(PASSAGE, FakeEngine())
    gw = out.ai.timing["generatedWith"]
    assert gw["settings"] == {"voice": "af_bella"} and gw["pronunciations"] == {"gaieties": "gayetees"}
    assert len(gw["hash"]) == 64


def test_a_recording_without_a_human_id_is_rejected_with_a_clear_message():
    import pytest

    with pytest.raises(ValueError, match="humanPassageId"):
        run_flow({k: v for k, v in PASSAGE.items() if k != "humanPassageId"}, FakeEngine(), recording_path="x.mp3")


def test_decode_audio_returns_mono_float_at_the_requested_rate(tmp_path):
    import pytest

    pytest.importorskip("av")
    sf = pytest.importorskip("soundfile")
    from asr_words import decode_audio

    tone = (0.3 * np.sin(np.linspace(0, 440 * 2 * np.pi, 22050))).astype(np.float32)
    path = tmp_path / "tone.wav"
    sf.write(path, tone, 22050)
    for rate in (16000, 24000):
        out = decode_audio(str(path), rate)
        assert out.dtype == np.float32 and out.ndim == 1
        assert abs(len(out) - rate) <= rate * 0.02  # about one second
        assert 0.2 < float(np.max(np.abs(out))) < 0.4


def test_soundalong_block_lists_both_voices_with_the_human_voice_first_and_flags(tmp_path):
    rec = tmp_path / "rec.mp3"
    rec.write_bytes(b"audio")
    recording = np.zeros(24000 * 5, dtype=np.float32)
    spoken = heard(["hello", "world", "we", "saw", "gaieties", "today"])
    both = run_flow(PASSAGE, FakeEngine(), recording_path=str(rec), transcribe_fn=lambda a: spoken, decode_fn=lambda p, r: recording)
    block = both.soundalong
    assert block["features"] == ["sa", "sahv"]
    sa = block["soundAlong"]
    assert sa["passageId"] == "ai-1" and sa["defaultVoice"] == "human"
    assert [v["kind"] for v in sa["voices"]] == ["human", "ai"]
    assert sa["voices"][0]["audio"] == "hu-1" and sa["voices"][0]["timing"] == "hu-1.timing.json"


def test_soundalong_block_for_an_ai_only_passage_defaults_to_the_ai_voice():
    block = run_flow({k: v for k, v in PASSAGE.items() if k != "humanPassageId"}, FakeEngine()).soundalong
    assert block["features"] == ["sa"] and block["soundAlong"]["defaultVoice"] == "ai"
    assert [v["kind"] for v in block["soundAlong"]["voices"]] == ["ai"]


def test_a_part_of_a_long_document_carries_its_series_in_the_timing_and_a_malformed_one_is_ignored():
    ids = [f"2b781dab-4521-40d2-a9b6-ad5f2bb0ba9{i}" for i in range(2)]
    series = {"id": "5af24980-4d6d-41c1-87fa-4f21cb2d169d", "index": 1, "total": 2, "title": "The Story", "partIds": ids}
    base = {k: v for k, v in PASSAGE.items() if k != "humanPassageId"}
    assert run_flow({**base, "series": series}, FakeEngine()).ai.timing["series"] == series
    assert "series" not in run_flow({**base, "series": {"id": "x"}}, FakeEngine()).ai.timing
    assert "series" not in run_flow(base, FakeEngine()).ai.timing
