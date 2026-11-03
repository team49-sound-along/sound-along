"""Generate a DRAFT question set for one passage: generate, validate, shuffle, verify. Nothing here is served to students."""
from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from qg_adapters import AdapterError, ModelAdapter
from qg_cost import Price, estimate_usd
from qg_extract import extract_json
from qg_passage import sentences_from_timing
from qg_prompt import PROMPT_VERSION, generation_messages
from qg_validate import shuffle_choices, too_similar, validate_question
from qg_verify import verify_question

MAX_QUESTIONS = 6
GENERATION_MAX_TOKENS = 3000  # reasoning models count their thinking against this


class GenerationError(RuntimeError):
    """The model's generation reply could not be used at all (not JSON, or no questions)."""


def _dropped(question: Any, reasons: list[str]) -> dict[str, Any]:
    text = question.get("question") if isinstance(question, Mapping) else None
    return {"question": str(text) if text else "(not a usable question)", "reasons": reasons}


def generate_draft(
    timing_doc: Mapping[str, Any],
    adapter: ModelAdapter,
    *,
    n: int = 4,
    seed: int = 7,
    model: str,
    price: Price | None,
    today: str,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    started = clock()
    sentences = sentences_from_timing(timing_doc)
    title = str(timing_doc.get("title", ""))
    count = min(max(n, 1), MAX_QUESTIONS)

    system, user = generation_messages(title, sentences, count)
    reply = adapter.complete(system, user, max_tokens=GENERATION_MAX_TOKENS, temperature=0.4)
    calls, tokens_in, tokens_out = 1, reply.input_tokens, reply.output_tokens
    try:
        raw_questions = extract_json(reply.text, require_key="questions")["questions"]
    except ValueError as error:
        raise GenerationError(f"the generation reply was not usable JSON: {error}") from error
    if not isinstance(raw_questions, list) or not raw_questions:
        raise GenerationError("the model returned no questions")

    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    seen: set[str] = set()
    accepted: list[dict[str, Any]] = []  # validated questions so far, for the near-duplicate check
    for position, raw in enumerate(raw_questions):
        question, reasons = validate_question(raw, sentences)
        if question is not None and question["question"].lower() in seen:
            question, reasons = None, ["duplicate of an earlier question"]
        if question is not None and any(too_similar(question, earlier) for earlier in accepted):
            question, reasons = None, ["too similar to an earlier question (it asks about the same fact)"]
        if question is None:
            dropped.append(_dropped(raw, reasons))
            continue
        seen.add(question["question"].lower())
        accepted.append(question)
        shuffled = shuffle_choices(question, seed, key=f"q{position}")
        try:
            result = verify_question(adapter, sentences, shuffled)
        except AdapterError as error:
            dropped.append(_dropped(shuffled, [f"verification failed: {error}"]))
            continue
        calls += 2
        tokens_in, tokens_out = tokens_in + result.input_tokens, tokens_out + result.output_tokens
        if not result.answered_from_passage:
            dropped.append(_dropped(shuffled, ["the model could not answer it correctly from the passage"]))
            continue
        kept.append(
            {
                "id": f"q{len(kept) + 1}",
                **shuffled,
                "checks": {"answeredFromPassage": True, "guessableWithoutPassage": result.guessable_without_passage},
                "review": {"status": "pending"},
            }
        )

    cost = estimate_usd(tokens_in, tokens_out, price)
    return {
        "version": 1,
        "passageId": timing_doc.get("id"),
        "title": title,
        "sentenceCount": len(sentences),
        "status": "draft",
        "generatedWith": {"model": model, "promptVersion": PROMPT_VERSION, "seed": seed, "date": today},
        "questions": kept,
        "dropped": dropped,
        "metrics": {
            "calls": calls,
            "inputTokens": tokens_in,
            "outputTokens": tokens_out,
            "seconds": round(clock() - started, 2),
            "estimatedCostUsd": None if cost is None else round(cost, 10),
            "priceBasis": price.basis if price else None,
        },
    }
