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
