import io
import json

import numpy as np

from engine import SAMPLE_RATE
from polly_engine import PollyEngine


class FakePolly:
    """Mimics boto3's polly client: one call for audio (pcm), one for word speech marks (json)."""

    def __init__(self, samples_16k: int, marks: list[dict]):
        self.pcm = (np.ones(samples_16k, dtype="<i2") * 1000).tobytes()
        self.marks = "\n".join(json.dumps(m) for m in marks).encode()
        self.calls: list[dict] = []

    def synthesize_speech(self, **kwargs):
        self.calls.append(kwargs)
        body = self.marks if kwargs["OutputFormat"] == "json" else self.pcm
        return {"AudioStream": io.BytesIO(body)}


MARKS = [
    {"time": 0, "type": "word", "start": 0, "end": 3, "value": "The"},
    {"time": 300, "type": "word", "start": 4, "end": 9, "value": "quick"},
    {"time": 700, "type": "word", "start": 10, "end": 14, "value": "fox."},
]


def test_audio_is_resampled_to_the_pipeline_rate_and_scaled_to_float():
    client = FakePolly(16000, MARKS)  # 1 second at 16 kHz
    out = PollyEngine(client).synthesize("The quick fox.")
    assert abs(len(out.audio) - SAMPLE_RATE) <= 2
    assert out.audio.dtype == np.float32 and 0.02 < float(out.audio[100]) < 0.04


def test_word_marks_become_tokens_ending_where_the_next_word_starts():
    out = PollyEngine(FakePolly(16000, MARKS)).synthesize("The quick fox.")
    assert [t.text for t in out.tokens] == ["The", "quick", "fox."]
    assert [(t.start_s, t.end_s) for t in out.tokens] == [(0.0, 0.3), (0.3, 0.7), (0.7, 1.0)]


def test_requests_neural_pcm_and_word_marks_with_the_same_voice():
    client = FakePolly(16000, MARKS)
    PollyEngine(client, voice="Joanna").synthesize("Hi there.")
    audio_call = next(c for c in client.calls if c["OutputFormat"] == "pcm")
    marks_call = next(c for c in client.calls if c["OutputFormat"] == "json")
    assert audio_call["Engine"] == marks_call["Engine"] == "neural"
    assert audio_call["VoiceId"] == marks_call["VoiceId"] == "Joanna"
    assert marks_call["SpeechMarkTypes"] == ["word"]


def test_non_word_marks_and_blank_lines_are_ignored():
    marks = MARKS + [{"time": 900, "type": "sentence", "start": 0, "end": 14, "value": "The quick fox."}]
    out = PollyEngine(FakePolly(16000, marks)).synthesize("The quick fox.")
    assert len(out.tokens) == 3


def test_empty_audio_returns_no_tokens():
    out = PollyEngine(FakePolly(0, [])).synthesize("")
    assert len(out.audio) == 0 and out.tokens == ()


# ---- Generative and long-form voices -----------------------------------------------------------------------------------------------
import pytest  # noqa: E402

from polly_engine import POLLY_VOICES, polly_voice_for  # noqa: E402


def test_a_generative_voice_makes_audio_only_and_leaves_the_word_times_to_the_recognizer():
    client = FakePolly(16000, MARKS)
    engine = PollyEngine(client, voice="Matthew", engine="generative")
    out = engine.synthesize("The quick fox.")
    assert engine.native_timing is False and out.tokens == () and len(out.audio) > 0
    assert [c["OutputFormat"] for c in client.calls] == ["pcm"]  # no speech-mark request: Polly does not return marks for generative voices
    assert all(c["Engine"] == "generative" for c in client.calls)


def test_neural_and_long_form_voices_keep_native_word_times():
    assert PollyEngine(FakePolly(16000, MARKS), voice="Lupe", engine="neural").native_timing is True
    assert PollyEngine(FakePolly(16000, MARKS), voice="Alba", engine="long-form").native_timing is True


def test_the_voice_catalogue_says_which_engine_each_spanish_voice_can_use():
    assert POLLY_VOICES["Lupe"]["lang"] == "es-US" and "neural" in POLLY_VOICES["Lupe"]["engines"]
    assert "long-form" in POLLY_VOICES["Alba"]["engines"] and POLLY_VOICES["Alba"]["lang"] == "es-ES"
    assert "neural" not in POLLY_VOICES["Carlos"]["engines"] and "generative" in POLLY_VOICES["Carlos"]["engines"]


def test_voice_and_engine_are_chosen_from_the_language_and_the_environment():
    assert polly_voice_for("en", {}) == ("Joanna", "neural")
    assert polly_voice_for("es", {}) == ("Lupe", "neural")
    assert polly_voice_for("es", {"POLLY_VOICE_ES": "Sergio", "POLLY_ENGINE": "generative"}) == ("Sergio", "generative")


def test_a_voice_that_cannot_use_the_chosen_engine_is_refused_before_any_billing():
    with pytest.raises(ValueError, match="Carlos"):
        polly_voice_for("es", {"POLLY_VOICE_ES": "Carlos", "POLLY_ENGINE": "neural"})
    with pytest.raises(ValueError, match="(?i)engine"):
        polly_voice_for("en", {"POLLY_ENGINE": "turbo"})
