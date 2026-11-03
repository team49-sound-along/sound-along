import numpy as np
import pytest

from asr_words import Heard, norm
from engine import SAMPLE_RATE, SentenceAudio
from engines import create_engine
from flow import run_flow
from word_mapper import EngineToken, map_words


def test_norm_ignores_accents_inverted_punctuation_and_case():
    assert norm("¡Allí!") == "alli"
    assert norm("niños,") == "ninos"
    assert norm("¿Qué?") == "que"
    assert norm("There's") == "theres"  # English is unchanged


def test_word_mapper_matches_accented_display_words_to_unaccented_engine_tokens():
    engine = [EngineToken("ninos", 0.0, 0.4), EngineToken("juegan", 0.4, 0.9)]
    out = map_words(["niños", "juegan"], engine)
    assert [w.aligned for w in out] == [True, True]


class SilentSpanishEngine:
    """Like Kokoro in Spanish: audio but NO word timing."""

    name = "kokoro"
    voice = "ef_dora"
    native_timing = False

    def synthesize(self, sentence: str) -> SentenceAudio:
        seconds = 0.4 * len(sentence.split())
        return SentenceAudio(np.full(int(seconds * SAMPLE_RATE), 0.1, dtype=np.float32), ())


def heard(words, step=0.4):
    return [Heard(w, i * step + 0.2, i * step + 0.2 + 0.3) for i, w in enumerate(words)]


SPANISH = {"uuid": "es-1", "title": "El parque", "language": "es", "content": "<p>Los niños juegan. Allí comen frutas.</p>"}


def test_spanish_word_times_come_from_the_recognizer_when_the_engine_has_none():
    calls = []

    def fake_transcribe(audio, language="en"):
        calls.append(language)
        return heard(["los", "niños", "juegan", "allí", "comen", "frutas"])

    out = run_flow(SPANISH, SilentSpanishEngine(), transcribe_fn=fake_transcribe)
    words = out.ai.timing["words"]
    assert calls == ["es"]
    assert out.ai.timing["language"] == "es"
    assert [w["aligned"] for w in words] == [True] * 6
    assert words[0]["start_ms"] == 200 and words[1]["start_ms"] == 600
    assert out.ai.timing["metrics"]["unalignedWords"] == 0


def test_the_quality_check_reuses_the_same_recognition_pass_for_spanish():
    calls = []

    def fake_transcribe(audio, language="en"):
        calls.append(language)
        return heard(["los", "niños", "juegan", "allí", "comen", "frutas"])

    out = run_flow({**SPANISH, "qualityCheck": True}, SilentSpanishEngine(), transcribe_fn=fake_transcribe)
    assert len(calls) == 1 and out.ai.timing["review"]["suspects"] == []


def test_english_keeps_native_engine_timing_and_calls_no_recognizer_without_a_check():
    class EnglishEngine(SilentSpanishEngine):
        native_timing = True
        voice = "af_heart"

        def synthesize(self, sentence):
            words = sentence.split()
            return SentenceAudio(np.full(int(0.4 * len(words) * SAMPLE_RATE), 0.1, dtype=np.float32),
                                 tuple(EngineToken(w.strip(".,"), i * 0.4, i * 0.4 + 0.3) for i, w in enumerate(words)))

    def boom(*_a, **_k):
        raise AssertionError("recognizer must not run")

    out = run_flow({"uuid": "en-1", "title": "T", "content": "<p>Hello world.</p>"}, EnglishEngine(), transcribe_fn=boom)
    assert out.ai.timing["language"] == "en" and out.ai.timing["words"][0]["start_ms"] == 0


def test_unknown_language_is_rejected_clearly():
    with pytest.raises(ValueError, match="language"):
        create_engine("kokoro", settings={}, language="fr")
