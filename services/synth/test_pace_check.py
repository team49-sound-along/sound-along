import numpy as np
import pytest

import pipeline
from engine import SAMPLE_RATE, SentenceAudio


class Fast:
    """An engine that returns almost no audio for a long text, as Kokoro did when it cut a long sentence off."""
    name, voice, native_timing = "fake", "v", True

    def __init__(self, seconds):
        self.seconds = seconds

    def synthesize(self, sentence):
        return SentenceAudio(np.zeros(int(self.seconds * SAMPLE_RATE), dtype=np.float32), ())


def html(words):
    return "<p>" + " ".join(["palabra"] * words) + ".</p>"


def test_narration_far_too_short_for_its_words_is_refused_instead_of_published():
    with pytest.raises(ValueError, match="too short"):
        pipeline.generate(html(300), Fast(5))


def test_normal_pace_is_accepted_and_short_texts_are_never_judged():
    pipeline.generate(html(300), Fast(110))  # about 160 words a minute
    pipeline.generate(html(12), Fast(0.5))
