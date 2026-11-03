"""Prompts for question generation and for the two answer checks, plus answer parsing."""
from __future__ import annotations

import re
from collections.abc import Sequence

from qg_extract import extract_json

PROMPT_VERSION = "q2"
LETTERS = "ABCD"

_GENERATION_SYSTEM = (
    "You write reading comprehension questions for children in grades 2 to 5. Use simple words and short sentences. "
    "Every question must be answerable from the passage alone, never from outside knowledge. "
    "Reply with JSON only, no other text."
)

_ANSWER_SYSTEM = 'You answer multiple-choice questions. Reply with JSON only, like {"answer": "B"}.'


def numbered(sentences: Sequence[str]) -> str:
    """The passage with one sentence per line and its number in square brackets, so evidence can be cited exactly."""
    return "\n".join(f"[{i}] {sentence}" for i, sentence in enumerate(sentences))


_EXAMPLE = (
    "Example passage:\n[0] Mia has a small brown dog named Pip.\n[1] Every morning they walk to the park.\n[2] Pip chases the ducks but never catches one.\n"
    'Example good question: {"skill": "literal", "question": "What does Pip do at the park?", "choices": ["He chases the ducks.", "He digs a hole.", "He sleeps all day."], '
    '"answerIndex": 0, "evidenceQuote": "Pip chases the ducks", "evidenceSentence": 2}\n'
    'Example BAD question: "Why is Mia happy?" (the passage never says she is happy).'
)


def generation_messages(title: str, sentences: Sequence[str], n: int) -> tuple[str, str]:
    user = (
        f"Passage title: {title}\n"
        "The passage, one sentence per line, each with its number:\n"
        f"{numbered(sentences)}\n\n"
        f"Write up to {n} multiple-choice questions about this passage. Write fewer, or an empty list, if the passage does not support good ones.\n"
        "Rules:\n"
        "- Exactly 3 choices per question. One is correct. The others sound reasonable but are clearly wrong according to the passage.\n"
        "- Each question tests ONE fact, and exactly one choice is supported by the passage. No other choice may also be true.\n"
        "- Do not assume anything the passage does not say (no invented feelings, favorites or reasons).\n"
        "- Ask about a main idea or an important detail, not a vague or trivial point.\n"
        "- Wrong choices must be the same kind of thing as the right one, about the same length, and never silly (not 'no park').\n"
        "- Keep each choice under 10 words. Never use 'all of the above' or 'none of the above'.\n"
        '- "skill" is "literal" when the answer is stated in one sentence, or "inferential" when the reader must combine sentences.\n'
        '- "evidenceQuote" is words copied exactly from the passage (at least 3 words) that prove the correct answer.\n'
        '- "evidenceSentence" is the number of the sentence that holds that quote.\n'
        '- "answerIndex" is the position (0, 1 or 2) of the correct choice in "choices".\n\n'
        f"{_EXAMPLE}\n\n"
        "Return JSON only, in exactly this shape:\n"
        '{"questions": [{"skill": "literal", "question": "...", "choices": ["...", "...", "..."], "answerIndex": 0, "evidenceQuote": "...", "evidenceSentence": 0}]}'
    )
    return _GENERATION_SYSTEM, user


def answer_messages(question: str, choices: Sequence[str], sentences: Sequence[str] | None) -> tuple[str, str]:
    """Ask the model to answer. With `sentences` it sees the passage; with None it sees only the question (the guessability check)."""
    intro = f"Passage:\n{numbered(sentences)}\n\n" if sentences is not None else "No passage is available. Choose the most likely answer.\n\n"
    options = "\n".join(f"{LETTERS[i]}. {choice}" for i, choice in enumerate(choices))
    return _ANSWER_SYSTEM, f"{intro}Question: {question}\n{options}\n\nReply with JSON like {{\"answer\": \"B\"}}."


_BARE_LETTER = re.compile(r"^\s*(?:answer\s*[:=\-]?\s*)?\(?([A-Da-d])\)?\s*\.?\s*$", re.IGNORECASE)


def parse_answer(text: str, choice_count: int) -> int | None:
    """The chosen choice index, or None when the reply is not a clear answer within the available choices."""
    value: object | None = None
    try:
        parsed = extract_json(text, require_key="answer")
        value = parsed["answer"]
    except ValueError:
        match = _BARE_LETTER.match(text or "")
        value = match.group(1) if match else None
    if isinstance(value, bool):
        return None
    index: int | None = None
    if isinstance(value, int):
        index = value
    elif isinstance(value, str) and len(value.strip()) == 1 and value.strip().upper() in LETTERS:
        index = LETTERS.index(value.strip().upper())
    return index if index is not None and 0 <= index < choice_count else None
