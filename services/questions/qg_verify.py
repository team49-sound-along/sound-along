"""The two model checks. Both use the same model that wrote the question, so they are filters, not proof: a person still reviews every question."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from qg_adapters import ModelAdapter
from qg_prompt import ANSWER_SCHEMA, answer_messages, parse_answer

ANSWER_MAX_TOKENS = 800  # reasoning models count their thinking against this, so it is not tiny


@dataclass(frozen=True)
class VerifyResult:
    answered_from_passage: bool  # with the passage, the model picked the intended answer
    guessable_without_passage: bool  # without the passage, the model STILL picked it (a flaw in generated items)
    picked_with_passage: int | None
    picked_without_passage: int | None
    input_tokens: int
    output_tokens: int


def _pick(adapter: ModelAdapter, question: Mapping[str, Any], sentences: Sequence[str] | None) -> tuple[int | None, int, int]:
    system, user = answer_messages(question["question"], question["choices"], sentences)
    reply = adapter.complete(system, user, max_tokens=ANSWER_MAX_TOKENS, temperature=0.0, json_schema=ANSWER_SCHEMA)
    return parse_answer(reply.text, len(question["choices"])), reply.input_tokens, reply.output_tokens


def verify_question(adapter: ModelAdapter, sentences: Sequence[str], question: Mapping[str, Any]) -> VerifyResult:
    with_passage, in_a, out_a = _pick(adapter, question, sentences)
    without_passage, in_b, out_b = _pick(adapter, question, None)
    right = question["answerIndex"]
    return VerifyResult(
        answered_from_passage=with_passage == right,
        guessable_without_passage=without_passage == right,
        picked_with_passage=with_passage,
        picked_without_passage=without_passage,
        input_tokens=in_a + in_b,
        output_tokens=out_a + out_b,
    )
