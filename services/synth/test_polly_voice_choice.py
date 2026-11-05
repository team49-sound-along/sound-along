"""Per-job Polly voice and voice quality (Settings -> job options -> engine)."""
import json
from pathlib import Path

import pytest

from mixed import ForeignSpan
from polly_engine import POLLY_VOICES, PollyEngine, canonical_voice, polly_choice
from test_polly_engine import MARKS, FakePolly

API_VOICES = Path(__file__).resolve().parents[1] / "api" / "config" / "polly-voices.json"


def test_the_generator_table_matches_the_settings_list_voice_for_voice():
    listed = json.loads(API_VOICES.read_text())
    assert len(listed) >= 15
    for v in listed:
        known = POLLY_VOICES[canonical_voice(v["id"])]
        assert known["lang"] == v["accent"], v["id"]
        assert set(v["engines"]) <= set(known["engines"]), v["id"]


def test_a_job_voice_overrides_the_deployment_default_for_its_language():
    assert polly_choice("en", {"voice": "Ruth"}, {}) == ("Ruth", "neural")
    assert polly_choice("es", {"voiceEs": "Mia"}, {"POLLY_VOICE_ES": "Lupe"}) == ("Mia", "neural")


def test_an_open_source_or_wrong_language_job_voice_falls_back_to_the_deployment_default():
    assert polly_choice("en", {"voice": "af_heart"}, {}) == ("Ruth", "neural")
    assert polly_choice("en", {"voice": "Lupe"}, {"POLLY_VOICE": "Matthew"}) == ("Matthew", "neural")
    assert polly_choice("es", {"voiceEs": "Ruth"}, {}) == ("Lupe", "neural")
    assert polly_choice("es", {"voiceEs": "Carlos"}, {})[0] == "Carlos"


def test_the_accented_spelling_of_a_voice_is_the_same_voice():
    assert canonical_voice("Andrés") == "Andres" and canonical_voice("Raúl") == "Raul"
    assert polly_choice("es", {"voiceEs": "Andrés"}, {})[0] == "Andres"


def test_generative_is_used_when_the_voice_supports_it_and_the_job_or_environment_asks():
    assert polly_choice("en", {"voice": "Ruth", "pollyEngine": "generative"}, {}) == ("Ruth", "generative")
    assert polly_choice("en", {"voice": "Ruth"}, {"POLLY_ENGINE": "generative"}) == ("Ruth", "generative")
    assert polly_choice("en", {"voice": "Ruth", "pollyEngine": "neural"}, {"POLLY_ENGINE": "generative"}) == ("Ruth", "neural")  # the teacher's choice wins


def test_a_voice_without_the_asked_quality_uses_the_one_it_has_instead_of_failing_the_job():
    assert polly_choice("en", {"voice": "Kendra", "pollyEngine": "generative"}, {}) == ("Kendra", "neural")
    assert polly_choice("es", {"voiceEs": "Carlos", "pollyEngine": "neural"}, {}) == ("Carlos", "generative")


def test_without_any_job_choice_the_deployment_rules_stay_strict():
    with pytest.raises(ValueError, match="Carlos"):
        polly_choice("es", {}, {"POLLY_VOICE_ES": "Carlos", "POLLY_ENGINE": "neural"})
    with pytest.raises(ValueError, match="(?i)engine"):
        polly_choice("en", {"pollyEngine": "turbo"}, {})


@pytest.mark.parametrize("voice,lang,text,word,foreign", [
    ("Ruth", "en", "Visit Mateo today.", "Mateo", "es"),
    ("Gregory", "en", "Visit Mateo today.", "Mateo", "es"),
    ("Mia", "es", "Me gusta el pizza hoy.", "pizza", "en"),
    ("Pedro", "es", "Me gusta el pizza hoy.", "pizza", "en"),
])
def test_every_voice_keeps_mixed_language_sentences_working_with_the_lang_tag(voice, lang, text, word, foreign):
    client = FakePolly(16000, MARKS)
    key = "voice" if lang == "en" else "voiceEs"
    chosen, engine = polly_choice(lang, {key: voice}, {})
    start = text.index(word)
    PollyEngine(client, voice=chosen, engine=engine).synthesize(text, [ForeignSpan(start, start + len(word), foreign)])
    tag = "es-US" if foreign == "es" else "en-US"
    assert any(f'xml:lang="{tag}"' in c["Text"] for c in client.calls)
    assert {c["VoiceId"] for c in client.calls} == {voice}


def test_a_generative_run_returns_audio_and_no_word_marks_so_the_recognizer_times_it():
    client = FakePolly(16000, MARKS)
    voice, engine = polly_choice("en", {"voice": "Matthew", "pollyEngine": "generative"}, {})
    out = PollyEngine(client, voice=voice, engine=engine).synthesize("The quick fox.")
    assert len(out.audio) > 0 and out.tokens == ()
    assert {c["Engine"] for c in client.calls} == {"generative"} and [c["OutputFormat"] for c in client.calls] == ["pcm"]
