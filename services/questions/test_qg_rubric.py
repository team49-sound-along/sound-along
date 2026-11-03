"""The rubric judge: prompt, verdict parsing, must-pass logic, and informational readability."""
import json

import pytest

from conftest import SENTENCES
from qg_adapters import FakeAdapter, ModelReply
from qg_rubric import CRITERIA, MUST_PASS, JudgeResult, count_syllables, judge_messages, judge_question, parse_verdicts, readability_grade

QUESTION = {"skill": "literal", "question": "Where is Piedmont Park?", "choices": ["In a small town.", "In Atlanta, Georgia.", "Far from any city."], "answerIndex": 1, "evidenceSentence": 2}


def verdicts(**overrides):
    base = {name: {"pass": True, "reason": "fine"} for name in CRITERIA}
    base.update(overrides)
    return json.dumps(base)


def test_the_judge_prompt_contains_everything_it_needs():
    system, user = judge_messages(SENTENCES, QUESTION)
    assert "[2] In Atlanta, Georgia" in user
    assert "Where is Piedmont Park?" in user
    assert "B. In Atlanta, Georgia." in user and "correct answer is B" in user
    for name in CRITERIA:
        assert name in user
    assert "JSON" in system + user


def test_every_verdict_is_parsed_with_its_reason():
    parsed = parse_verdicts(verdicts(noFalsePremise={"pass": False, "reason": "assumes a favorite"}))
    assert parsed["noFalsePremise"] == (False, "assumes a favorite")
    assert parsed["oneCorrectAnswer"] == (True, "fine")


def test_missing_or_malformed_verdicts_are_unknown_not_failures():
    parsed = parse_verdicts('{"oneCorrectAnswer": {"pass": true, "reason": "ok"}, "worthAsking": "yes"}')
    assert parsed["oneCorrectAnswer"][0] is True
    assert parsed["worthAsking"] == (None, "")
    assert parsed["noFalsePremise"] == (None, "")
    assert all(value == (None, "") for value in parse_verdicts("not json at all").values())


def test_only_must_pass_criteria_can_fail_a_question():
    assert set(MUST_PASS) == {"oneCorrectAnswer", "noFalsePremise", "appropriate"}
    soft = judge_question(FakeAdapter([ModelReply(verdicts(worthAsking={"pass": False, "reason": "trivia"}), 300, 50)]), SENTENCES, QUESTION)
    assert soft.must_pass_failed == [] and soft.flags == ["worthAsking"]
    hard = judge_question(FakeAdapter([ModelReply(verdicts(oneCorrectAnswer={"pass": False, "reason": "two answers"}), 300, 50)]), SENTENCES, QUESTION)
    assert hard.must_pass_failed == ["oneCorrectAnswer"] and hard.reasons["oneCorrectAnswer"] == "two answers"
    assert (hard.input_tokens, hard.output_tokens) == (300, 50)


def test_unknown_must_pass_verdicts_are_listed_for_the_human_not_failed():
    result = judge_question(FakeAdapter(["I cannot judge this"]), SENTENCES, QUESTION)
    assert result.must_pass_failed == [] and set(result.unknown) == set(CRITERIA)


def test_syllables_and_readability_are_informational():
    assert count_syllables("park") == 1 and count_syllables("nature") == 2 and count_syllables("different") == 3
    easy = readability_grade("The cat sat. It was fun.")
    hard = readability_grade("Notwithstanding considerable circumstantial difficulties, the commissioners deliberated extensively.")
    assert easy < 3 < 10 < hard
    assert readability_grade("") == 0.0
