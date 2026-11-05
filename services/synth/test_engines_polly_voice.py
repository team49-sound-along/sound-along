"""create_engine passes the job's Polly voice and voice quality to the engine (a fake boto3 module, no AWS)."""
import sys
import types

import pytest

from engines import create_engine


@pytest.fixture(autouse=True)
def fake_boto3(monkeypatch):
    made = []
    module = types.ModuleType("boto3")
    module.client = lambda service, region_name=None, **kwargs: made.append((service, region_name)) or object()
    monkeypatch.setitem(sys.modules, "boto3", module)
    monkeypatch.delenv("TTS_ENGINE", raising=False)
    monkeypatch.delenv("POLLY_VOICE", raising=False)
    monkeypatch.delenv("POLLY_VOICE_ES", raising=False)
    monkeypatch.delenv("POLLY_ENGINE", raising=False)
    return made


def test_the_job_voice_is_used_for_english():
    engine = create_engine(settings={"ttsEngine": "polly", "voice": "Ruth", "voiceEs": "Mia"})
    assert (engine.name, engine.voice, engine._engine) == ("polly", "Ruth", "neural")


def test_the_job_spanish_voice_is_used_for_spanish():
    engine = create_engine(settings={"ttsEngine": "polly", "voice": "Ruth", "voiceEs": "Mia"}, language="es")
    assert (engine.voice, engine._engine) == ("Mia", "neural")


def test_voice_quality_generative_means_no_native_word_times():
    engine = create_engine(settings={"ttsEngine": "polly", "voice": "Ruth", "pollyEngine": "generative"})
    assert engine._engine == "generative" and engine.native_timing is False


def test_an_open_source_voice_saved_with_polly_uses_the_deployment_default(monkeypatch):
    monkeypatch.setenv("POLLY_VOICE", "Matthew")
    engine = create_engine(settings={"ttsEngine": "polly", "voice": "phonon_hadley"})
    assert engine.voice == "Matthew"
