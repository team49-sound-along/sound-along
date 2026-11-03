"""The rubric judge: a SEPARATE model scores each question against written criteria.

Criteria 1 (grounded: the quote matches the passage) and 4 (needs the passage) are checked without a judge, elsewhere. The judge scores the rest.
Only MUST_PASS criteria can drop a question, and only when the judge clearly says "fail". An unclear or failed judge call is passed to the human reviewer.
Readability is informational only: grade formulas on short answer choices are noise.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from qg_adapters import ModelAdapter
from qg_extract import extract_json
from qg_prompt import LETTERS, numbered

CRITERIA = ("oneCorrectAnswer", "noFalsePremise", "worthAsking", "goodDistractors", "appropriate")
MUST_PASS = ("oneCorrectAnswer", "noFalsePremise", "appropriate")
JUDGE_MAX_TOKENS = 1200  # a reasoning judge counts its thinking against this

_DEFINITIONS = {
    "oneCorrectAnswer": "Exactly one choice is correct according to the passage. If another choice could also be defended from the passage, it fails.",
    "noFalsePremise": "The question assumes nothing the passage does not say (no invented 'favorite', 'reason' or 'feeling' that the text never states).",
    "worthAsking": "It tests a main idea or an important detail, not a trivial or vague point.",
    "goodDistractors": "The wrong choices are plausible, similar in kind and length, and clearly wrong according to the passage. None is silly.",
    "appropriate": "It is suitable for children: no sensitive, harmful or inappropriate content.",
}

_SYSTEM = (
    "You are a strict reviewer of reading comprehension questions for children. Judge ONLY from the passage given. "
    "Be skeptical: if you are unsure a criterion is met, it fails. "
    "Do not think out loud. Your whole reply is one JSON object that starts with { and keeps every reason to one short sentence."
)


@dataclass(frozen=True)
class JudgeResult:
    verdicts: dict[str, bool | None]  # True passed, False failed, None the judge gave no clear verdict
    reasons: dict[str, str]
    input_tokens: int
    output_tokens: int

    @property
    def must_pass_failed(self) -> list[str]:
        return [name for name in CRITERIA if name in MUST_PASS and self.verdicts.get(name) is False]

    @property
    def flags(self) -> list[str]:
        """Soft criteria the judge failed. They do not drop a question; the reviewer sees them."""
        return [name for name in CRITERIA if name not in MUST_PASS and self.verdicts.get(name) is False]

    @property
    def unknown(self) -> list[str]:
        return [name for name in CRITERIA if self.verdicts.get(name) is None]


def judge_messages(sentences: Sequence[str], question: Mapping[str, Any]) -> tuple[str, str]:
    options = "\n".join(f"{LETTERS[i]}. {choice}" for i, choice in enumerate(question["choices"]))
    criteria = "\n".join(f"- {name}: {text}" for name, text in _DEFINITIONS.items())
    shape = ", ".join(f'"{name}": {{"pass": true, "reason": "..."}}' for name in CRITERIA)
    user = (
        f"Passage, one sentence per line with its number:\n{numbered(sentences)}\n\n"
        f"Question: {question['question']}\n{options}\n"
        f"The intended correct answer is {LETTERS[question['answerIndex']]}.\n\n"
        f"Score each criterion pass or fail, with a short reason:\n{criteria}\n\n"
        f"Return JSON only, in exactly this shape:\n{{{shape}}}"
    )
    return _SYSTEM, user


def parse_verdicts(text: str) -> dict[str, tuple[bool | None, str]]:
    """Each criterion becomes (passed, reason). Anything missing or malformed is (None, "") so it is shown to a person, never counted as a failure."""
    try:
        data = extract_json(text)
    except ValueError:
        data = {}
    result: dict[str, tuple[bool | None, str]] = {}
    for name in CRITERIA:
        entry = data.get(name) if isinstance(data, Mapping) else None
        if isinstance(entry, Mapping) and isinstance(entry.get("pass"), bool):
            result[name] = (entry["pass"], str(entry.get("reason", "")))
        else:
            result[name] = (None, "")
    return result


def judge_question(adapter: ModelAdapter, sentences: Sequence[str], question: Mapping[str, Any]) -> JudgeResult:
    system, user = judge_messages(sentences, question)
    reply = adapter.complete(system, user, max_tokens=JUDGE_MAX_TOKENS, temperature=0.0)
    parsed = parse_verdicts(reply.text)
    return JudgeResult(
        verdicts={name: passed for name, (passed, _) in parsed.items()},
        reasons={name: reason for name, (_, reason) in parsed.items() if reason},
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
    )


# ---- readability (informational) -----------------------------------------------------------------------------------
def count_syllables(word: str) -> int:
    letters = re.sub(r"[^a-z]", "", word.lower())
    if not letters:
        return 0
    groups = len(re.findall(r"[aeiouy]+", letters))
    if letters.endswith("e") and not letters.endswith(("le", "ee")) and groups > 1:
        groups -= 1  # a silent final e, as in "nature"
    return max(groups, 1)


def readability_grade(text: str) -> float:
    """Flesch-Kincaid grade level, never below 0. Informational only."""
    words = re.findall(r"[A-Za-z']+", text)
    sentences = max(len(re.findall(r"[.!?]+", text)), 1)
    if not words:
        return 0.0
    syllables = sum(count_syllables(w) for w in words)
    return round(max(0.39 * len(words) / sentences + 11.8 * syllables / len(words) - 15.59, 0.0), 1)
