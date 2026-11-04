"""Optional AWS services, all off by default: Amazon Translate (translateModel=amazon) and Amazon Polly narration (ttsEngine=polly)."""
from __future__ import annotations

import pytest

from sound_along.config import parse_polly_options, parse_translate_model, parse_tts_engine
from tests.helpers import actions_for_roles_starting_with, synth
from tests.test_translate_model import generator


def env(template) -> dict:
    return {v["Name"]: v["Value"] for v in [{"Name": k, "Value": val} for k, val in generator(template)["Environment"]["Variables"].items()]}


def generator_actions(template) -> list[str]:
    return actions_for_roles_starting_with(template, "GeneratorFunctionServiceRole")


def test_by_default_the_generator_may_call_neither_translate_nor_polly():
    t = synth()
    acts = generator_actions(t)
    assert not any(a.startswith(("translate:", "polly:", "bedrock:")) for a in acts)
    assert "TTS_ENGINE" not in env(t) and "TRANSLATE_MODEL" not in env(t)


@pytest.mark.parametrize("value", ["amazon", "amazon:informal", "amazon:formal"])
def test_amazon_translate_grants_only_translate_text_and_no_bedrock(value):
    t = synth(translate_model=value)
    acts = generator_actions(t)
    assert "translate:TranslateText" in acts and not any(a.startswith(("bedrock:", "polly:")) for a in acts)
    assert env(t)["TRANSLATE_MODEL"] == value


def test_amazon_translate_does_not_cap_the_generator_at_one_concurrent_run():
    props = generator(synth(translate_model="amazon:informal"))
    assert props.get("ReservedConcurrentExecutions") == 2


def test_polly_narration_grants_synthesize_speech_only_and_sets_the_engine_and_voices():
    t = synth(tts_engine="polly", polly_options=(("POLLY_VOICE_ES", "Lucia"), ("POLLY_ENGINE", "neural")))
    acts = generator_actions(t)
    assert "polly:SynthesizeSpeech" in acts and not any(a.startswith(("translate:", "bedrock:")) for a in acts)
    e = env(t)
    assert e["TTS_ENGINE"] == "polly" and e["POLLY_VOICE_ES"] == "Lucia" and e["POLLY_ENGINE"] == "neural"


@pytest.mark.parametrize("value,expect", [("amazon", "amazon"), ("amazon:informal", "amazon:informal"), ("bedrock:amazon.nova-lite-v1:0", "bedrock:amazon.nova-lite-v1:0"), (None, None)])
def test_translate_model_accepts_amazon_and_bedrock(value, expect):
    assert parse_translate_model(value) == expect


@pytest.mark.parametrize("value", ["amazon:casual", "amazon:", "azure", "amazon ", 5])
def test_translate_model_refuses_anything_else(value):
    with pytest.raises(ValueError, match="translateModel"):
        parse_translate_model(value)


def test_tts_engine_and_polly_options_are_validated():
    assert parse_tts_engine(None) == "kokoro" and parse_tts_engine("Polly") == "polly"
    with pytest.raises(ValueError, match="ttsEngine"):
        parse_tts_engine("eleven")
    assert parse_polly_options("Joanna", "Lupe", "Generative") == {"POLLY_VOICE": "Joanna", "POLLY_VOICE_ES": "Lupe", "POLLY_ENGINE": "generative"}
    assert parse_polly_options(None, None, None) == {}
    with pytest.raises(ValueError):
        parse_polly_options("Joanna; rm", None, None)
    with pytest.raises(ValueError, match="pollyEngine"):
        parse_polly_options(None, None, "turbo")
