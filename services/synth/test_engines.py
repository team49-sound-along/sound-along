import pytest

from engines import create_engine


def test_unknown_engine_is_rejected_with_a_clear_message():
    with pytest.raises(ValueError, match="Use 'kokoro', 'phonon' or 'polly'"):
        create_engine("espeak")


def test_the_jobs_tts_engine_setting_beats_the_deployment_default(monkeypatch):
    monkeypatch.setenv("TTS_ENGINE", "kokoro")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    engine = create_engine(settings={"voice": "af_heart", "ttsEngine": "polly"})
    assert engine.name == "polly" and engine.voice == "Joanna"


def test_an_unknown_tts_engine_setting_is_rejected(monkeypatch):
    monkeypatch.delenv("TTS_ENGINE", raising=False)
    with pytest.raises(ValueError, match="Unknown TTS_ENGINE"):
        create_engine(settings={"ttsEngine": "espeak"})
