"""Deterministic checks on a generated question (no model involved) and a seeded shuffle of its choices."""
from __future__ import annotations

import random
import re
from collections.abc import Mapping, Sequence
from typing import Any

SKILLS = ("literal", "inferential")
QUESTION_MIN, QUESTION_MAX = 10, 160
CHOICE_MAX = 80
CHOICES_ALLOWED = (3, 4)
_BANNED_CHOICES = ("all of the above", "none of the above", "both a and b")
_STOPWORDS = frozenset(
    "that this with from there their they have were what when where which about into than them then been some would could should also "
    "will your these those other only very just over under after before because".split()
)


def content_words(text: str) -> set[str]:
    """Lower-case words of four or more letters that are not stopwords. Used to check an answer against its evidence."""
    return {w for w in re.findall(r"[a-z']+", text.lower()) if len(w) >= 4 and w not in _STOPWORDS}


def validate_shape(raw: Any, sentence_count: int) -> tuple[dict[str, Any] | None, list[str]]:
    """Schema and range checks. Returns (normalised question or None, reasons it failed)."""
    if not isinstance(raw, Mapping):
        return None, ["the question is not an object"]
    reasons: list[str] = []
    question = str(raw.get("question", "")).strip()
    if not QUESTION_MIN <= len(question) <= QUESTION_MAX:
        reasons.append(f"question text must be {QUESTION_MIN} to {QUESTION_MAX} characters")
    raw_choices = raw.get("choices")
    choices = [str(c).strip() for c in raw_choices] if isinstance(raw_choices, Sequence) and not isinstance(raw_choices, str) else []
    if len(choices) not in CHOICES_ALLOWED:
        reasons.append("choices: need 3 or 4")
    if any(not c or len(c) > CHOICE_MAX for c in choices):
        reasons.append(f"choices must be non-empty and at most {CHOICE_MAX} characters")
    if len({c.lower() for c in choices}) != len(choices):
        reasons.append("choices are not unique")
    if any(any(banned in c.lower() for banned in _BANNED_CHOICES) for c in choices):
        reasons.append("choices must not use 'all of the above' or 'none of the above'")
    answer = raw.get("answerIndex")
    if isinstance(answer, bool) or not isinstance(answer, int) or not 0 <= answer < max(len(choices), 1):
        reasons.append("answerIndex must be the position of a choice")
    evidence = raw.get("evidenceSentence")
    if isinstance(evidence, bool) or not isinstance(evidence, int) or not 0 <= evidence < sentence_count:
        reasons.append(f"evidenceSentence must be a sentence number from 0 to {sentence_count - 1}")
    skill = raw.get("skill")
    if skill not in SKILLS:
        reasons.append("skill must be 'literal' or 'inferential'")
    if reasons:
        return None, reasons
    return {"skill": skill, "question": question, "choices": choices, "answerIndex": answer, "evidenceSentence": evidence}, []


def normalize_text(text: str) -> str:
    """Lower case, curly quotes straightened, punctuation and extra spaces removed, so a quote matches despite formatting."""
    straight = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    return " ".join(re.sub(r"[^a-z0-9' ]+", " ", straight.lower()).split())


MIN_QUOTE_WORDS = 3


def locate_quote(quote: str, sentences: Sequence[str]) -> int | None:
    """Number of the sentence that contains the quote (the first, if several do), or None when no sentence does."""
    wanted = normalize_text(quote)
    if len(wanted.split()) < MIN_QUOTE_WORDS:
        return None
    for number, sentence in enumerate(sentences):
        if wanted in normalize_text(sentence):
            return number
    return None


def validate_question(raw: Any, sentences: Sequence[str]) -> tuple[dict[str, Any] | None, list[str]]:
    """Shape checks, then the evidence check.

    With an `evidenceQuote` (prompt q2): the quote must appear in the passage, else the question is dropped; a wrong `evidenceSentence` is
    corrected to the sentence that holds the quote. Without one (prompt q1): a literal answer must share a content word with its sentence.
    """
    question, reasons = validate_shape(raw, len(sentences))
    if question is None:
        return None, reasons
    quote = raw.get("evidenceQuote") if isinstance(raw, Mapping) else None
    if isinstance(quote, str) and quote.strip():
        found = locate_quote(quote, sentences)
        if found is None:
            return None, ["the evidence quote is not in the passage (or is shorter than 3 words)"]
        question = {**question, "evidenceQuote": quote.strip(), "evidenceSentence": found}
        if found != raw.get("evidenceSentence"):
            question["evidenceCorrected"] = True
    if question["skill"] == "literal":
        answer_words = content_words(question["choices"][question["answerIndex"]])
        if answer_words and not answer_words & content_words(sentences[question["evidenceSentence"]]):
            return None, ["the right answer has no word overlap with its evidence sentence"]
    return question, []


SIMILARITY_LIMIT = 0.5  # share of content words in common (question text plus the RIGHT answer) above which two questions ask the same thing


def _signature(question: Mapping[str, Any]) -> set[str]:
    return content_words(question["question"]) | content_words(question["choices"][question["answerIndex"]])


def too_similar(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """True when two questions ask about the same fact, even in different words. Wrong answers and choice order are ignored."""
    first, second = _signature(a), _signature(b)
    union = first | second
    return bool(union) and len(first & second) / len(union) >= SIMILARITY_LIMIT


def shuffle_choices(question: Mapping[str, Any], seed: int, key: str) -> dict[str, Any]:
    """A copy with the choices in a seeded order (models like to put the right answer first). The input is never changed."""
    order = list(range(len(question["choices"])))
    random.Random(f"{seed}:{key}").shuffle(order)
    return {**question, "choices": [question["choices"][i] for i in order], "answerIndex": order.index(question["answerIndex"])}
