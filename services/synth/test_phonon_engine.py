"""Phonon engine: voice choice, pronunciation respellings, sample rate and how the factory picks it. No `ptts` wheel needed."""
import numpy as np
import pytest

from engine import SAMPLE_RATE
from engines import create_engine, engine_for_voice
from phonon_engine import PHONON_VOICES, PhononEngine, apply_respellings


class FakeTTS:
    sample_rate = SAMPLE_RATE

    def __init__(self):
        self.calls = []

    def synth(self, text, *, voice=None, **_):
        self.calls.append((text, voice))
        return np.full(int(0.5 * SAMPLE_RATE), 0.1, dtype=np.float64)  # float64 on purpose: the engine must return float32


def test_the_two_listening_test_winners_are_the_only_voices():
    assert PHONON_VOICES == {"phonon_hadley": "Hadley", "phonon_everly": "Everly"}


def test_synthesize_speaks_the_catalog_voice_and_returns_float32_audio_with_no_word_tokens():
    tts = FakeTTS()
    engine = PhononEngine(voice="phonon_hadley", tts=tts)
    out = engine.synthesize("Hello there.")
    assert tts.calls == [("Hello there.", "Hadley")]
    assert out.audio.dtype == np.float32 and out.audio.ndim == 1 and len(out.audio) == SAMPLE_RATE // 2
    assert out.tokens == ()  # Phonon gives no word times: the flow takes them from the recognizer
    assert engine.native_timing is False and engine.name == "phonon" and engine.voice == "phonon_hadley"


def test_unknown_voice_is_rejected_with_the_valid_ones_named():
    with pytest.raises(ValueError, match="phonon_everly"):
        PhononEngine(voice="phonon_nobody", tts=FakeTTS())


def test_a_model_at_another_sample_rate_is_refused_not_silently_played_at_the_wrong_speed():
    tts = FakeTTS()
    tts.sample_rate = 16_000
    with pytest.raises(ValueError, match="24000"):
        PhononEngine(voice="phonon_everly", tts=tts)


def test_empty_audio_gives_an_empty_result_instead_of_crashing():
    tts = FakeTTS()
    tts.synth = lambda text, **_: np.zeros(0)
    out = PhononEngine(voice="phonon_everly", tts=tts).synthesize("...")
    assert len(out.audio) == 0 and out.tokens == ()


def test_respellings_replace_whole_words_only_keep_case_insensitivity_and_skip_phoneme_entries():
    fixes = {"gaieties": "gay uh teez", "park": "/pɑːk/", "tea": "tee"}
    assert apply_respellings("Gaieties and gaiety, teas and tea.", fixes) == "Gay uh teez and gaiety, teas and tee."
    assert apply_respellings("A park.", fixes) == "A park."  # "/phonemes/" are Kokoro-only
    assert apply_respellings("Nothing to fix.", {}) == "Nothing to fix."


def test_the_engine_applies_respellings_before_speaking():
    tts = FakeTTS()
    PhononEngine(voice="phonon_everly", respellings={"gaieties": "gay uh teez"}, tts=tts).synthesize("The gaieties began.")
    assert tts.calls[0][0] == "The gay uh teez began."


def test_generated_with_records_that_phonon_ignored_the_speed_setting():
    from flow import run_flow

    tts = FakeTTS()
    passage = {"uuid": "p", "title": "T", "content": "<p>Hello there.</p>", "settings": {"voice": "phonon_hadley", "speed": 0.8}}
    out = run_flow(passage, PhononEngine(voice="phonon_hadley", tts=tts), transcribe_fn=lambda audio: [], decode_fn=None)
    assert out.ai.timing["generatedWith"]["speedApplied"] is False


def test_the_factory_picks_the_engine_from_the_voice():
    assert engine_for_voice("phonon_hadley") == "phonon" and engine_for_voice("af_heart") is None and engine_for_voice(None) is None


def test_create_engine_builds_phonon_for_a_phonon_voice_even_when_the_default_engine_is_kokoro(monkeypatch):
    import phonon_engine

    monkeypatch.setattr(phonon_engine, "load_tts", lambda: FakeTTS())
    monkeypatch.setenv("TTS_ENGINE", "kokoro")
    engine = create_engine(settings={"voice": "phonon_everly", "speed": 0.9}, respellings={})
    assert (engine.name, engine.voice) == ("phonon", "phonon_everly")


def test_a_phonon_voice_is_not_valid_for_spanish():
    with pytest.raises(ValueError, match="Spanish"):
        create_engine(settings={"voiceEs": "phonon_hadley"}, language="es")


# --- fixes from the independent review ---------------------------------------------------------------------------------------------
def test_phonon_refuses_spanish_text(monkeypatch):
    import phonon_engine

    monkeypatch.setattr(phonon_engine, "load_tts", lambda: FakeTTS())
    with pytest.raises(ValueError, match="English"):
        create_engine("phonon", settings={"voice": "phonon_hadley"}, language="es")


def test_choosing_the_phonon_engine_without_a_phonon_voice_uses_hadley(monkeypatch):
    import phonon_engine

    monkeypatch.setattr(phonon_engine, "load_tts", lambda: FakeTTS())
    for settings in (None, {}, {"voice": "af_heart"}):
        assert create_engine("phonon", settings=settings, respellings={}).voice == "phonon_hadley"


def test_a_voice_that_is_not_a_string_is_not_a_crash():
    assert engine_for_voice(["phonon_hadley"]) is None and engine_for_voice({"a": 1}) is None and engine_for_voice(3) is None


def test_respellings_match_keys_that_end_in_punctuation_and_keep_a_leading_capital():
    assert apply_respellings("St. Paul's church", {"st.": "saint"}) == "Saint Paul's church"
    assert apply_respellings("Tea is hot. tea is good.", {"tea": "tee"}) == "Tee is hot. tee is good."


def test_load_tts_uses_the_baked_folders_the_thread_count_and_loads_only_once(monkeypatch):
    import sys
    import types

    import phonon_engine

    made = []

    class RealisticTTS:
        sample_rate = SAMPLE_RATE

        def __init__(self, model, **kw):
            made.append((model, kw))

    threads = []
    fake = types.SimpleNamespace(TTS=RealisticTTS, set_num_threads=threads.append)
    monkeypatch.setitem(sys.modules, "ptts", fake)
    monkeypatch.setitem(phonon_engine._TTS, "unused", None)
    phonon_engine._TTS.clear()
    monkeypatch.setenv("PHONON_MODEL_DIR", "/opt/phonon/model")
    monkeypatch.setenv("PHONON_VOICES_DIR", "/opt/phonon/voices")
    monkeypatch.setenv("PHONON_THREADS", "3")
    first, second = phonon_engine.load_tts(), phonon_engine.load_tts()
    phonon_engine._TTS.clear()
    assert first is second and len(made) == 1 and threads == [3]
    assert made[0] == ("/opt/phonon/model", {"lang": "en", "device": "cpu", "voice_catalog": "/opt/phonon/voices"})
