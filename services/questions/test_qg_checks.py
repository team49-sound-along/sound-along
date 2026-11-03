"""Deterministic validation, deterministic shuffling, the two model checks, and cost."""
import copy

import pytest

from conftest import SENTENCES
from qg_adapters import FakeAdapter, ModelReply
from qg_cost import PRICES, estimate_usd, price_for
from qg_validate import shuffle_choices, validate_question
from qg_verify import verify_question


# ---- validate ------------------------------------------------------------------------------------------------------
def test_a_good_question_is_normalised_and_accepted(good_raw):
    question, reasons = validate_question(good_raw, SENTENCES)
    assert reasons == [] and question is not None
    assert question["question"] == "Where is Piedmont Park?"
    assert question["answerIndex"] == 0 and question["evidenceSentence"] == 2


def bad(good_raw, **changes):
    raw = copy.deepcopy(good_raw)
    raw.update(changes)
    return raw


@pytest.mark.parametrize(
    "changes, reason",
    [
        ({"question": ""}, "question"),
        ({"question": "Hi?"}, "question"),
        ({"question": "x" * 200 + "?"}, "question"),
        ({"choices": ["Only one."]}, "choices"),
        ({"choices": ["a", "b", "c", "d", "e"]}, "choices"),
        ({"choices": ["In Atlanta, Georgia.", "in atlanta, georgia.", "Far from any city."]}, "unique"),
        ({"choices": ["In Atlanta, Georgia.", "All of the above", "Far from any city."]}, "above"),
        ({"choices": ["In Atlanta, Georgia.", "None of the above", "Far from any city."]}, "above"),
        ({"choices": ["In Atlanta, Georgia.", "", "Far from any city."]}, "choices"),
        ({"answerIndex": 5}, "answerIndex"),
        ({"answerIndex": "A"}, "answerIndex"),
        ({"answerIndex": True}, "answerIndex"),
        ({"evidenceSentence": 9}, "evidence"),
        ({"evidenceSentence": -1}, "evidence"),
        ({"skill": "trivia"}, "skill"),
    ],
)
def test_bad_questions_are_dropped_with_a_reason(good_raw, changes, reason):
    question, reasons = validate_question(bad(good_raw, **changes), SENTENCES)
    assert question is None
    assert any(reason in r for r in reasons), reasons


def test_a_literal_question_must_be_supported_by_its_evidence_sentence(good_raw):
    off_topic = bad(good_raw, evidenceSentence=1)  # "People can play on the grass." has nothing about Atlanta
    question, reasons = validate_question(off_topic, SENTENCES)
    assert question is None and any("overlap" in r for r in reasons)


def test_an_inferential_question_is_exempt_from_the_word_overlap_rule(good_raw):
    inferential = bad(good_raw, skill="inferential", evidenceSentence=1)
    question, reasons = validate_question(inferential, SENTENCES)
    assert reasons == [] and question is not None


def test_non_dict_input_is_rejected():
    question, reasons = validate_question("not a dict", SENTENCES)
    assert question is None and reasons


# ---- shuffle -------------------------------------------------------------------------------------------------------
def test_shuffle_keeps_the_right_answer_and_is_deterministic(good_raw):
    question, _ = validate_question(good_raw, SENTENCES)
    first = shuffle_choices(question, seed=7, key="q1")
    again = shuffle_choices(question, seed=7, key="q1")
    assert first == again
    assert first["choices"][first["answerIndex"]] == "In Atlanta, Georgia."
    assert sorted(first["choices"]) == sorted(question["choices"])


def test_shuffle_never_mutates_its_input(good_raw):
    question, _ = validate_question(good_raw, SENTENCES)
    before = copy.deepcopy(question)
    shuffle_choices(question, seed=3, key="q9")
    assert question == before


def test_shuffle_moves_the_answer_away_from_slot_zero_across_many_questions(good_raw):
    question, _ = validate_question(good_raw, SENTENCES)
    positions = {shuffle_choices(question, seed=1, key=f"q{n}")["answerIndex"] for n in range(40)}
    assert len(positions) >= 2


# ---- verify --------------------------------------------------------------------------------------------------------
def a_question(good_raw):
    question, _ = validate_question(good_raw, SENTENCES)
    return question


def test_verify_marks_answerable_and_not_guessable(good_raw):
    q = a_question(good_raw)
    fake = FakeAdapter([ModelReply('{"answer": "A"}', 100, 5), ModelReply('{"answer": "B"}', 40, 5)])
    result = verify_question(fake, SENTENCES, q)
    assert result.answered_from_passage is True
    assert result.guessable_without_passage is False
    assert (result.input_tokens, result.output_tokens) == (140, 10)


def test_verify_flags_a_question_the_model_can_guess_without_the_passage(good_raw):
    q = a_question(good_raw)
    fake = FakeAdapter(['{"answer": "A"}', '{"answer": "A"}'])
    result = verify_question(fake, SENTENCES, q)
    assert result.answered_from_passage is True and result.guessable_without_passage is True


def test_verify_marks_a_question_unanswerable_when_the_model_picks_wrongly(good_raw):
    q = a_question(good_raw)
    fake = FakeAdapter(['{"answer": "C"}', '{"answer": "C"}'])
    assert verify_question(fake, SENTENCES, q).answered_from_passage is False


def test_verify_treats_an_unparseable_answer_as_a_failed_check(good_raw):
    q = a_question(good_raw)
    result = verify_question(FakeAdapter(["I am not sure", "no idea"]), SENTENCES, q)
    assert result.answered_from_passage is False and result.guessable_without_passage is False


def test_the_without_passage_call_really_has_no_passage(good_raw):
    q = a_question(good_raw)
    fake = FakeAdapter(['{"answer": "A"}', '{"answer": "B"}'])
    verify_question(fake, SENTENCES, q)
    with_passage_user, without_passage_user = fake.calls[0][1], fake.calls[1][1]
    assert "Atlanta, Georgia, there is a big park" in with_passage_user
    assert "there is a big park" not in without_passage_user


# ---- cost ----------------------------------------------------------------------------------------------------------
def test_price_table_is_labelled_with_its_region_basis():
    price = price_for("ollama:gpt-oss:20b")
    assert price is not None and price.input_per_million == 0.0721 and price.output_per_million == 0.3090
    assert "Sydney" in price.basis
    assert price_for("bedrock:openai.gpt-oss-20b-1:0") == price
    assert price_for("ollama:unknown-model") is None


def test_estimate_usd_uses_per_million_prices():
    price = PRICES["gpt-oss-20b"]
    assert estimate_usd(1_000_000, 1_000_000, price) == pytest.approx(0.0721 + 0.3090)
    assert estimate_usd(5_500, 1_000, price) == pytest.approx(5_500 * 0.0721 / 1e6 + 1_000 * 0.3090 / 1e6)
    assert estimate_usd(0, 0, price) == 0.0
    assert estimate_usd(10, 10, None) is None


# ---- near-duplicate questions --------------------------------------------------------------------------------------
from qg_validate import too_similar


def asked(text, right, evidence=2):
    return {"skill": "literal", "question": text, "choices": [right, "Wrong one.", "Other wrong."], "answerIndex": 0, "evidenceSentence": evidence}


def test_the_same_fact_asked_in_different_words_is_too_similar():
    first = asked("Where is Piedmont Park?", "In Atlanta, Georgia.")
    second = asked("In which city is Piedmont Park located?", "In Atlanta, Georgia.")
    assert too_similar(first, second) is True


def test_different_facts_are_not_too_similar():
    first = asked("Where is Piedmont Park?", "In Atlanta, Georgia.")
    second = asked("What can people do on the grass?", "Play.", evidence=1)
    assert too_similar(first, second) is False


def test_too_similar_ignores_the_order_of_the_choices_and_wrong_answers():
    first = asked("Where is Piedmont Park?", "In Atlanta, Georgia.")
    second = {**asked("Where is Piedmont Park?", "In Atlanta, Georgia."), "choices": ["Mars.", "Moon.", "In Atlanta, Georgia."], "answerIndex": 2}
    assert too_similar(first, second) is True


# ---- evidence quote (prompt q2) ------------------------------------------------------------------------------------
def test_a_quote_that_matches_keeps_the_question_and_its_sentence(good_raw):
    question, reasons = validate_question(bad(good_raw, evidenceQuote="there is a big park called Piedmont Park"), SENTENCES)
    assert reasons == [] and question["evidenceSentence"] == 2 and "evidenceCorrected" not in question


def test_a_wrong_evidence_sentence_is_corrected_from_the_quote(good_raw):
    question, _ = validate_question(bad(good_raw, evidenceSentence=3, evidenceQuote="In Atlanta, Georgia, there is a big park"), SENTENCES)
    assert question["evidenceSentence"] == 2 and question["evidenceCorrected"] is True


def test_a_quote_not_in_the_passage_drops_the_question(good_raw):
    question, reasons = validate_question(bad(good_raw, evidenceQuote="the park has a giant fountain"), SENTENCES)
    assert question is None and "quote" in reasons[0]


def test_a_very_short_quote_is_not_accepted(good_raw):
    question, reasons = validate_question(bad(good_raw, evidenceQuote="big park"), SENTENCES)
    assert question is None and "quote" in reasons[0]


def test_quote_matching_ignores_case_curly_quotes_and_punctuation():
    from qg_validate import locate_quote
    assert locate_quote("DOUG’S favorite spot is the wetlands", ["x y z.", "Doug's favorite spot is the Wetlands!"]) == 1
