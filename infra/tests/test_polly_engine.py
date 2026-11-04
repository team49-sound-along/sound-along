"""Provisioning for TTS_ENGINE=polly: the generator gets the env vars and the polly:SynthesizeSpeech permission,
and kokoro (the default) provisions neither."""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from sound_along.config import TtsConfig
from sound_along.stack import SoundAlongStack, SoundAlongStackProps
from tests.helpers import SOURCES, actions_for_roles_starting_with


def _synth(tts: TtsConfig, cms_host: str = "ec2") -> Template:
    app = cdk.App()
    stack = SoundAlongStack(
        app,
        "TestStack",
        props=SoundAlongStackProps(alert_email="test@example.com", cms_host=cms_host, sources=SOURCES, tts=tts),
        env=cdk.Environment(region="us-west-2"),
    )
    return Template.from_stack(stack)


def _generator_env(template: Template) -> dict[str, object]:
    for fn in template.find_resources("AWS::Lambda::Function").values():
        if fn["Properties"].get("PackageType") == "Image":
            return fn["Properties"]["Environment"]["Variables"]
    raise AssertionError("no container (generator) Lambda found")


def test_kokoro_default_adds_no_polly_env_and_no_polly_permission() -> None:
    template = _synth(TtsConfig())
    env = _generator_env(template)
    assert "TTS_ENGINE" not in env and "POLLY_VOICE" not in env
    actions = actions_for_roles_starting_with(template, "GeneratorFunctionServiceRole")
    assert not [a for a in actions if a.startswith("polly:")]
    assert template.to_json()["Outputs"]["TtsEngine"]["Value"] == "kokoro"


def test_polly_sets_engine_env_and_default_voices() -> None:
    env = _generator_env(_synth(TtsConfig(engine="polly")))
    assert env["TTS_ENGINE"] == "polly"
    assert env["POLLY_VOICE"] == "Joanna"
    assert env["POLLY_VOICE_ES"] == "Lupe"


def test_polly_voices_are_overridable() -> None:
    env = _generator_env(_synth(TtsConfig(engine="polly", polly_voice="Matthew", polly_voice_es="Mia")))
    assert env["POLLY_VOICE"] == "Matthew" and env["POLLY_VOICE_ES"] == "Mia"


def test_polly_grants_only_synthesize_speech_on_the_generator_role() -> None:
    template = _synth(TtsConfig(engine="polly"))
    actions = actions_for_roles_starting_with(template, "GeneratorFunctionServiceRole")
    polly_actions = [a for a in actions if a.startswith("polly:")]
    assert polly_actions == ["polly:SynthesizeSpeech"], polly_actions
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [Match.object_like({"Action": "polly:SynthesizeSpeech", "Effect": "Allow", "Resource": "*"})]
                )
            }
        },
    )


def test_polly_output_reports_the_engine() -> None:
    template = _synth(TtsConfig(engine="polly"))
    assert template.to_json()["Outputs"]["TtsEngine"]["Value"] == "polly"
