"""Passage sentences, JSON extraction, prompts and answer parsing."""
import pytest

from conftest import SENTENCES, make_timing
from qg_extract import extract_json
from qg_passage import sentences_from_timing
from qg_prompt import PROMPT_VERSION, answer_messages, generation_messages, numbered, parse_answer


# ---- passage -------------------------------------------------------------------------------------------------------
def test_sentences_are_rebuilt_from_the_timing_words(timing):
    assert sentences_from_timing(timing) == SENTENCES


def test_empty_or_gappy_sentence_numbers_are_rejected():
    with pytest.raises(ValueError):
        sentences_from_timing({"words": []})
    gappy = make_timing(["One two.", "Three four."])
    for word in gappy["words"]:
        word["sentence"] *= 2  # numbers 0 and 2: the evidence index would no longer match a list position
    with pytest.raises(ValueError):
        sentences_from_timing(gappy)


# ---- JSON extraction -----------------------------------------------------------------------------------------------
def test_extract_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_from_code_fence_and_surrounding_prose():
    assert extract_json('Here you go:\n```json\n{"a": [1, 2]}\n```\nHope that helps.') == {"a": [1, 2]}
    assert extract_json('Sure. {"a": 1} Anything else?') == {"a": 1}


def test_extract_ignores_braces_inside_strings():
    assert extract_json('{"q": "use } and { carefully"}') == {"q": "use } and { carefully"}


def test_extract_prefers_the_object_with_the_required_key():
    text = 'Thinking: {"note": "scratch"} Final: {"questions": []}'
    assert extract_json(text, require_key="questions") == {"questions": []}


def test_extract_raises_when_there_is_no_json():
    with pytest.raises(ValueError):
        extract_json("no json here")
    with pytest.raises(ValueError):
        extract_json('{"a": ')
    with pytest.raises(ValueError):
        extract_json('{"a": 1}', require_key="questions")


# ---- prompts -------------------------------------------------------------------------------------------------------
def test_numbered_passage_uses_sentence_numbers():
    assert numbered(["One.", "Two."]) == "[0] One.\n[1] Two."


def test_generation_prompt_has_the_passage_the_count_and_the_contract():
    system, user = generation_messages("Park Day", SENTENCES, 4)
    assert "[0] A city park" in user and "[3] Many families" in user
    assert "Park Day" in user
    assert "4" in user
    for needed in ("evidenceSentence", "evidenceQuote", "answerIndex", "choices", "JSON"):
        assert needed in user or needed in system
    assert "grade" in (system + user).lower()
    assert PROMPT_VERSION


def test_answer_prompt_with_and_without_the_passage():
    with_passage = answer_messages("Where?", ["A", "B", "C"], SENTENCES)
    without = answer_messages("Where?", ["A", "B", "C"], None)
    assert "[2] In Atlanta" in with_passage[1]
    assert "Atlanta" not in without[1] and "[0]" not in without[1]
    assert "Where?" in without[1] and "A." in without[1] and "C." in without[1]


@pytest.mark.parametrize(
    "text, expected",
    [('{"answer": "B"}', 1), ('{"answer": "a"}', 0), ('{"answer": 2}', 2), ("Answer: C", 2), ("B", 1), ('{"answer": "Z"}', None), ("I cannot tell", None), ("", None)],
)
def test_parse_answer_accepts_letters_and_indexes(text, expected):
    assert parse_answer(text, choice_count=4) == expected


def test_parse_answer_rejects_an_index_outside_the_choices():
    assert parse_answer('{"answer": "D"}', choice_count=3) is None
    assert parse_answer('{"answer": 3}', choice_count=3) is None
