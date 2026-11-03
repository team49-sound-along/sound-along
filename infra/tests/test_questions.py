"""The question-drafting Lambda: bounded spend, narrow permissions, and best effort (it can never fail an audio job)."""
from __future__ import annotations

import json
from typing import Any

import pytest
from aws_cdk.assertions import Match, Template

from sound_along.config import parse_questions_enabled, parse_questions_model
from tests.helpers import FIXTURES, SOURCES, synth

MODEL = "bedrock:openai.gpt-oss-20b-1:0"
ARN = "arn:aws:bedrock:us-west-2::foundation-model/openai.gpt-oss-20b-1:0"


def questions_function(template: Template) -> dict[str, Any]:
    found = {k: v for k, v in template.find_resources("AWS::Lambda::Function").items() if v["Properties"].get("Handler") == "qg_handler.handler"}
    assert len(found) == 1, "expected exactly one questions function"
    return next(iter(found.values()))


def role_statements(template: Template, role_prefix: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for policy in template.find_resources("AWS::IAM::Policy").values():
        if any(r["Ref"].startswith(role_prefix) for r in policy["Properties"]["Roles"]):
            out += policy["Properties"]["PolicyDocument"]["Statement"]
    return out


def actions(statement: dict[str, Any]) -> list[str]:
    raw = statement["Action"]
    return [raw] if isinstance(raw, str) else list(raw)


def definition(template: Template) -> dict[str, Any]:
    machine = next(iter(template.find_resources("AWS::StepFunctions::StateMachine").values()))
    raw = machine["Properties"]["DefinitionString"]
    parts = raw["Fn::Join"][1] if isinstance(raw, dict) else [raw]
    return json.loads("".join(p if isinstance(p, str) else "REF" for p in parts))


# ---- the function ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["ec2", "lambda"])
def test_function_is_small_arm64_python_314_with_hard_spend_limits(mode: str) -> None:
    fn = questions_function(synth(mode))["Properties"]
    assert fn["Runtime"] == "python3.14" and fn["Architectures"] == ["arm64"]
    assert (fn["MemorySize"], fn["Timeout"], fn["ReservedConcurrentExecutions"]) == (256, 120, 2)


def test_without_a_model_it_is_off_has_no_model_setting_and_no_bedrock_permission_anywhere() -> None:
    template = synth()
    env = questions_function(template)["Properties"]["Environment"]["Variables"]
    assert env["QUESTIONS_ENABLED"] == "false" and "QUESTIONS_MODEL" not in env
    assert env["QUESTIONS_REGION"] == "us-west-2" and env["QUESTIONS_COUNT"] == "4"
    every_action = [a for s in json.loads(json.dumps(template.find_resources("AWS::IAM::Policy"))).values() for st in s["Properties"]["PolicyDocument"]["Statement"] for a in actions(st)]
    assert not [a for a in every_action if a.startswith("bedrock:")], "no model chosen means no Bedrock permission at all"


def test_enabling_without_a_model_is_still_off() -> None:
    env = questions_function(synth(questions_enabled=True))["Properties"]["Environment"]["Variables"]
    assert env["QUESTIONS_ENABLED"] == "false"


def test_with_a_model_the_switch_is_explicit_and_only_that_one_model_may_be_invoked() -> None:
    template = synth(questions_model=MODEL)
    env = questions_function(template)["Properties"]["Environment"]["Variables"]
    assert env["QUESTIONS_MODEL"] == MODEL and env["QUESTIONS_ENABLED"] == "false"  # a model alone does not switch it on
    assert questions_function(synth(questions_model=MODEL, questions_enabled=True))["Properties"]["Environment"]["Variables"]["QUESTIONS_ENABLED"] == "true"
    bedrock = [s for s in role_statements(template, "QuestionsFunctionServiceRole") if any(a.startswith("bedrock:") for a in actions(s))]
    assert len(bedrock) == 1 and actions(bedrock[0]) == ["bedrock:InvokeModel"] and bedrock[0]["Resource"] == ARN


def test_s3_access_is_read_data_list_data_and_write_only_raw_questions() -> None:
    statements = role_statements(synth(questions_model=MODEL), "QuestionsFunctionServiceRole")
    s3_statements = [s for s in statements if any(a.startswith("s3:") for a in actions(s))]
    by_action = {a: s for s in s3_statements for a in actions(s)}
    assert set(by_action) == {"s3:GetObject", "s3:ListBucket", "s3:PutObject"}
    assert "/data/*" in json.dumps(by_action["s3:GetObject"]["Resource"]) and "raw" not in json.dumps(by_action["s3:GetObject"]["Resource"])
    assert json.dumps(by_action["s3:PutObject"]["Resource"]).count("raw/questions/*") == 1 and "/data/" not in json.dumps(by_action["s3:PutObject"]["Resource"])
    assert by_action["s3:ListBucket"]["Condition"]["StringLike"]["s3:prefix"] == ["data/*"]
    assert not [a for s in statements for a in actions(s) if a.endswith("*")], "no wildcard actions"
    assert not [s for s in s3_statements if "s3:PutObject" in actions(s) and "data/" in json.dumps(s["Resource"])]


def test_the_function_gets_its_own_one_week_log_group() -> None:
    template = synth()
    assert template.find_resources("AWS::Logs::LogGroup", {"Properties": {"RetentionInDays": 7}})


def test_reserved_concurrency_is_totalled_so_a_small_account_quota_is_visible() -> None:
    """API 5 + generator 2 + questions 2. AWS keeps a minimum unreserved pool, so a quota of 10 leaves little room (see DEPLOY.md)."""
    template = synth("lambda")
    reserved = sorted(v["Properties"]["ReservedConcurrentExecutions"] for v in template.find_resources("AWS::Lambda::Function").values()
                      if "ReservedConcurrentExecutions" in v["Properties"])
    assert reserved == [2, 2, 5] and sum(reserved) == 9


# ---- the state machine -----------------------------------------------------------------------------------------------------------
def test_questions_run_only_after_a_generator_that_reported_done() -> None:
    states = definition(synth())["States"]
    choice = next(s for s in states.values() if s["Type"] == "Choice")
    rule = choice["Choices"][0]
    assert rule["Variable"] == "$.status" and rule["StringEquals"] == "done" and rule["Next"] == "InvokeQuestions"
    assert states["InvokeGenerator"]["Next"] == next(n for n, s in states.items() if s is choice)
    assert "Default" in choice and choice["Default"] != "InvokeQuestions"  # a failed or skipped job goes straight to the end


def test_a_questions_failure_is_caught_and_can_never_fail_the_job() -> None:
    states = definition(synth())["States"]
    step = states["InvokeQuestions"]
    assert step["Catch"][0]["ErrorEquals"] == ["States.ALL"]
    handler = states[step["Catch"][0]["Next"]]
    assert handler["Type"] == "Pass" and handler.get("End") is True
    assert step["Retry"] if "Retry" in step else True  # no automatic retry loop that could multiply spend
    assert "Retry" not in step


def test_the_generator_step_is_unchanged_and_still_retries_throttling() -> None:
    gen = definition(synth())["States"]["InvokeGenerator"]
    assert gen["Retry"][0]["MaxAttempts"] == 1 and "Lambda.TooManyRequestsException" in gen["Retry"][0]["ErrorEquals"]


# ---- context values --------------------------------------------------------------------------------------------------------------
def test_the_model_context_must_be_a_bedrock_model_id_or_absent() -> None:
    assert parse_questions_model(None) is None and parse_questions_model(MODEL) == MODEL
    for bad in ("openai.gpt-oss-20b-1:0", "ollama:gpt-oss:20b", "bedrock:", "bedrock:a b", "bedrock:*", "bedrock:a/../b", 5, ""):
        with pytest.raises(ValueError, match="questionsModel"):
            parse_questions_model(bad)


def test_the_switch_context_is_true_only_for_true() -> None:
    assert [parse_questions_enabled(v) for v in (None, "false", "no", "1", "TRUE ", "true", True)] == [False, False, False, False, False, True, True]
