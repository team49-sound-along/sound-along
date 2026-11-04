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


@pytest.mark.parametrize("value", [None, "bedrock:vendor.model-v1:0"])
def test_valid_values_parse(value) -> None:
    assert parse_translate_model(value) == value


@pytest.mark.parametrize("value", ["", "model", "bedrock:", "bedrock:../x", "bedrock:a b", 5, "arn:aws:bedrock:us-west-2::foundation-model/x"])
def test_anything_else_is_refused(value) -> None:
    with pytest.raises(ValueError, match="translateModel"):
        parse_translate_model(value)


# ---- cross-region profiles, one caller at a time, and spacing ---------------------------------------------------------------------
PROFILE = "bedrock:us.amazon.nova-lite-v1:0"


def role_bedrock(template, role_prefix):
    out = []
    for policy in template.find_resources("AWS::IAM::Policy").values():
        if any(r["Ref"].startswith(role_prefix) for r in policy["Properties"]["Roles"]):
            out += [s for s in policy["Properties"]["PolicyDocument"]["Statement"] if "bedrock:InvokeModel" in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])]
    return out


def test_a_cross_region_profile_id_gets_the_profile_and_only_its_own_foundation_model_through_that_profile() -> None:
    statements = role_bedrock(synth(translate_model=PROFILE), "GeneratorFunctionServiceRole")
    assert len(statements) == 2
    text = json.dumps(statements)
    assert "inference-profile/us.amazon.nova-lite-v1:0" in text and "AWS::Account" in text
    models = next(s for s in statements if "foundation-model" in json.dumps(s["Resource"]))
    assert sorted(models["Resource"]) == sorted(f"arn:aws:bedrock:{r}::foundation-model/amazon.nova-lite-v1:0" for r in ("us-east-1", "us-east-2", "us-west-2"))
    assert "bedrock:InferenceProfileArn" in json.dumps(models["Condition"]), "the foundation model is reachable only through that profile"
    assert not [a for s in statements for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"]) if a.endswith("*")]


def test_a_plain_model_id_still_gets_exactly_one_foundation_model_statement() -> None:
    statements = role_bedrock(synth(translate_model=MODEL), "GeneratorFunctionServiceRole")
    assert len(statements) == 1 and statements[0]["Resource"] == ARN and "Condition" not in statements[0]


def test_the_same_rules_apply_to_the_questions_function() -> None:
    statements = role_bedrock(synth(questions_model=PROFILE), "QuestionsFunctionServiceRole")
    assert len(statements) == 2 and "inference-profile/us.amazon.nova-lite-v1:0" in json.dumps(statements)
    assert len(role_bedrock(synth(questions_model="bedrock:amazon.nova-lite-v1:0"), "QuestionsFunctionServiceRole")) == 1


def reserved(template):
    return {k: v["Properties"]["ReservedConcurrentExecutions"] for k, v in template.find_resources("AWS::Lambda::Function").items() if "ReservedConcurrentExecutions" in v["Properties"]}


def test_a_bedrock_caller_gets_one_slot_and_a_function_without_bedrock_keeps_two() -> None:
    plain = sorted(reserved(synth("lambda")).values())
    assert plain == [2, 2, 5]
    both = sorted(reserved(synth("lambda", translate_model=MODEL, questions_model=MODEL, questions_enabled=True)).values())
    assert both == [1, 1, 5]
    only_translate = sorted(reserved(synth("lambda", translate_model=MODEL)).values())
    assert only_translate == [1, 2, 5]


def test_each_caller_waits_2_2_seconds_when_both_are_on_and_1_1_when_only_one_is() -> None:
    template = synth(translate_model=MODEL, questions_model=MODEL, questions_enabled=True)
    assert generator(template)["Environment"]["Variables"]["TRANSLATE_MIN_INTERVAL"] == "2.2"
    questions = next(v for v in template.find_resources("AWS::Lambda::Function").values() if v["Properties"].get("Handler") == "qg_handler.handler")
    assert questions["Properties"]["Environment"]["Variables"]["QUESTIONS_MIN_INTERVAL"] == "2.2"
    only = synth(translate_model=MODEL)
    assert generator(only)["Environment"]["Variables"]["TRANSLATE_MIN_INTERVAL"] == "1.1"
    assert "TRANSLATE_MIN_INTERVAL" not in generator(synth())["Environment"]["Variables"]


def test_the_model_id_check_accepts_both_forms() -> None:
    assert parse_translate_model("bedrock:amazon.nova-lite-v1:0") and parse_translate_model(PROFILE) == PROFILE
