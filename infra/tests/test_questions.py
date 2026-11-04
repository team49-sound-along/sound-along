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
def states_of(template: Template) -> dict[str, Any]:
    """Every state: the top-level ones plus those inside the Map that runs the parts."""
    top = definition(template)["States"]
    states = dict(top)
    for state in top.values():
        if state.get("Type") == "Map":
            states.update((state.get("ItemProcessor") or state.get("Iterator"))["States"])
    return states


def test_follow_up_steps_run_only_after_a_generator_that_reported_done() -> None:
    states = states_of(synth())
    first = states["InvokeGenerator"]["Next"]
    gate = states[first]
    assert gate["Type"] == "Choice" and gate["Choices"][0]["Variable"] == "$.status" and gate["Choices"][0]["StringEquals"] == "done"
    assert states[gate["Default"]]["Type"] == "Succeed"  # a failed job ends here: no questions, no translation


def test_questions_are_for_english_passages_only_and_translation_follows_either_way() -> None:
    states = states_of(synth())
    gate = states[states["InvokeGenerator"]["Next"]]
    language = states[gate["Choices"][0]["Next"]]
    assert language["Type"] == "Choice" and language["Choices"][0]["Variable"] == "$.language" and language["Choices"][0]["StringEquals"] == "en"
    assert language["Choices"][0]["Next"] == "InvokeQuestions" and language["Default"] == "InvokeTranslation"
    assert states["InvokeQuestions"]["Next"] == "InvokeTranslation"


def test_the_questions_result_is_added_to_the_state_not_replacing_it_so_the_next_step_still_has_the_passage_id() -> None:
    step = states_of(synth())["InvokeQuestions"]
    assert step["ResultPath"] == "$.questions" and "OutputPath" not in step


def test_a_questions_failure_is_caught_continues_to_translation_and_can_never_fail_the_job() -> None:
    states = states_of(synth())
    step = states["InvokeQuestions"]
    assert step["Catch"][0]["ErrorEquals"] == ["States.ALL"] and "Retry" not in step
    skipped = states[step["Catch"][0]["Next"]]
    assert skipped["Type"] == "Pass" and skipped["Next"] == "InvokeTranslation"


def test_translation_is_a_second_invocation_of_the_generator_with_its_own_failure_handling() -> None:
    template = synth()
    step = states_of(template)["InvokeTranslation"]
    payload = json.dumps(step["Parameters"])
    assert '"mode": "translate"' in payload and "$.passageId" in payload and "$.jobId" in payload
    assert step["Catch"][0]["ErrorEquals"] == ["States.ALL"]
    skipped = states_of(template)[step["Catch"][0]["Next"]]
    assert skipped["Type"] == "Pass" and skipped.get("End") is True
    retry = step["Retry"]
    assert len(retry) == 1 and retry[0]["ErrorEquals"] == ["Lambda.TooManyRequestsException"] and retry[0]["MaxAttempts"] == 2  # only a throttle is retried
    generator_arn = json.dumps(states_of(template)["InvokeGenerator"]["Resource"])
    assert json.dumps(step["Parameters"]["FunctionName"]) == json.dumps(states_of(template)["InvokeGenerator"]["Parameters"]["FunctionName"]), generator_arn


def test_the_generator_step_is_unchanged_and_still_retries_throttling() -> None:
    gen = states_of(synth())["InvokeGenerator"]
    assert gen["Retry"][0]["MaxAttempts"] == 1 and "Lambda.TooManyRequestsException" in gen["Retry"][0]["ErrorEquals"]


def test_the_whole_execution_is_given_eight_hours_which_covers_twelve_parts_that_each_take_the_worst_case() -> None:
    machine = next(iter(synth().find_resources("AWS::StepFunctions::StateMachine").values()))
    assert json.loads("".join(p if isinstance(p, str) else "REF" for p in machine["Properties"]["DefinitionString"]["Fn::Join"][1]))["TimeoutSeconds"] == 28800


# ---- context values --------------------------------------------------------------------------------------------------------------
def test_the_model_context_must_be_a_bedrock_model_id_or_absent() -> None:
    assert parse_questions_model(None) is None and parse_questions_model(MODEL) == MODEL
    for bad in ("openai.gpt-oss-20b-1:0", "ollama:gpt-oss:20b", "bedrock:", "bedrock:a b", "bedrock:*", "bedrock:a/../b", 5, ""):
        with pytest.raises(ValueError, match="questionsModel"):
            parse_questions_model(bad)


def test_the_switch_context_is_true_only_for_true() -> None:
    assert [parse_questions_enabled(v) for v in (None, "false", "no", "1", "TRUE ", "true", True)] == [False, False, False, False, False, True, True]


def test_the_parts_of_a_document_run_one_at_a_time_from_a_list_of_keys_and_a_crashed_part_does_not_stop_the_next() -> None:
    top = definition(synth())["States"]
    each = top["EachPart"]
    assert each["Type"] == "Map" and each["ItemsPath"] == "$.parts" and each["MaxConcurrency"] == 1 and each["ResultPath"] is None
    assert top[definition(synth())["StartAt"]]["Type"] == "Map" and each.get("End") is True
    inner = (each.get("ItemProcessor") or each.get("Iterator"))["States"]
    catch = inner["InvokeGenerator"]["Catch"][0]
    assert catch["ErrorEquals"] == ["States.ALL"] and inner[catch["Next"]]["Type"] == "Task"  # records the failure, then the next part runs


def test_a_crashed_part_has_its_job_marked_failed_so_it_never_stays_running_or_blocks_new_work() -> None:
    template = synth()
    inner = states_of(template)
    catch = inner["InvokeGenerator"]["Catch"][0]
    step = inner[catch["Next"]]
    assert catch["Next"] == "PartFailed" and step["Type"] == "Task" and "updateItem" in json.dumps(step["Resource"])
    params = json.dumps(step["Parameters"])
    assert '"failed"' in params and "$.jobId" in params and "attribute_exists(pk)" in params
    assert inner[step["Catch"][0]["Next"]]["Type"] == "Pass", "recording the failure is best effort"
