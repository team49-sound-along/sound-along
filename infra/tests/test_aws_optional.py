"""Optional AWS services, all off by default: Amazon Translate (translateModel=amazon) and Amazon Polly narration (ttsEngine=polly)."""
from __future__ import annotations

import json

import pytest

from sound_along.config import TtsConfig, parse_polly_engine, parse_polly_voice, parse_translate_model, parse_tts_engine
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
    t = synth(tts=TtsConfig(engine="polly", polly_voice_es="Lucia", polly_engine="neural"))
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
    assert parse_tts_engine(None) == "kokoro" and parse_tts_engine("polly") == "polly"
    with pytest.raises(ValueError, match="ttsEngine"):
        parse_tts_engine("eleven")
    assert parse_polly_voice("Lupe", "pollyVoiceEs") == "Lupe" and parse_polly_voice(None, "pollyVoice") is None
    assert parse_polly_engine("Generative") == "generative" and parse_polly_engine(None) is None
    with pytest.raises(ValueError, match="pollyVoice"):
        parse_polly_voice("Joanna; rm", "pollyVoice")
    with pytest.raises(ValueError, match="pollyEngine"):
        parse_polly_engine("turbo")


def test_the_polly_engine_is_only_set_when_chosen():
    assert "POLLY_ENGINE" not in TtsConfig(engine="polly").env()
    assert TtsConfig(engine="polly", polly_engine="long-form").env()["POLLY_ENGINE"] == "long-form"
    assert TtsConfig(polly_engine="generative").env() == {}  # Kokoro needs no environment, whatever Polly options are given


def test_the_pipeline_passes_the_optional_switches_to_the_deploy_and_only_those_that_were_set():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template
    from sound_along.pipeline_stack import PipelineStack, PipelineStackProps

    def build(**extra):
        app = cdk.App()
        stack = PipelineStack(app, "P", props=PipelineStackProps(github_owner="o", github_repo="r", **extra), env=cdk.Environment(region="us-west-2"))
        return json.dumps(Template.from_stack(stack).to_json())

    plain = build()
    assert "pollyVoice" not in plain and "translateModel" not in plain
    full = build(tts_engine="polly", extra_context=(("pollyVoiceEs", "Lupe"), ("pollyEngine", "generative"), ("translateModel", "amazon:informal")))
    for flag in ("-c ttsEngine=polly", "-c pollyVoiceEs=Lupe", "-c pollyEngine=generative", "-c translateModel=amazon:informal"):
        assert flag in full, flag
