"""The optional Bedrock translator: no model means no Bedrock permission; a model means one InvokeModel permission for exactly that model."""
from __future__ import annotations

import json

import pytest

from sound_along.config import parse_translate_model
from tests.helpers import synth

MODEL = "bedrock:example.model-v1:0"
ARN = "arn:aws:bedrock:us-west-2::foundation-model/example.model-v1:0"


def generator(template):
    found = {k: v for k, v in template.find_resources("AWS::Lambda::Function").items() if v["Properties"].get("PackageType") == "Image"}
    assert len(found) == 1
    return next(iter(found.values()))["Properties"]


def bedrock_statements(template):
    out = []
    for policy in template.find_resources("AWS::IAM::Policy").values():
        for st in policy["Properties"]["PolicyDocument"]["Statement"]:
            raw = st["Action"]
            if any(a.startswith("bedrock:") for a in ([raw] if isinstance(raw, str) else raw)):
                out.append(st)
    return out


def test_without_a_translate_model_the_generator_has_no_setting_and_the_stack_has_no_bedrock_permission_for_it() -> None:
    template = synth()
    env = generator(template)["Environment"]["Variables"]
    assert "TRANSLATE_MODEL" not in env and "TRANSLATE_REGION" not in env
    assert bedrock_statements(template) == []


def test_with_a_translate_model_the_generator_may_invoke_exactly_that_model() -> None:
    template = synth(translate_model=MODEL)
    env = generator(template)["Environment"]["Variables"]
    assert env["TRANSLATE_MODEL"] == MODEL and env["TRANSLATE_REGION"] == "us-west-2"
    (statement,) = bedrock_statements(template)
    assert statement["Action"] == "bedrock:InvokeModel" and statement["Resource"] == ARN and statement["Effect"] == "Allow"


@pytest.mark.parametrize("value", [None, "bedrock:anthropic.model-v1:0"])
def test_valid_values_parse(value) -> None:
    assert parse_translate_model(value) == value


@pytest.mark.parametrize("value", ["", "model", "bedrock:", "bedrock:../x", "bedrock:a b", 5, "arn:aws:bedrock:us-west-2::foundation-model/x"])
def test_anything_else_is_refused(value) -> None:
    with pytest.raises(ValueError, match="translateModel"):
        parse_translate_model(value)
