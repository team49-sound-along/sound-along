"""Context-aware translation with a language model on Amazon Bedrock, in front of the Opus-MT translator.

Why: Opus-MT translates one sentence at a time, so it cannot know that "su" means "her" because Ana is a girl, or that "a great deal" is a bargain.
A language model that sees the sentences around it can. This module has the same shape as the Opus-MT model (a function from a list of sentences
to a list of sentences), so `translate_passage`, the sentence map and the language switch do not change.

Safety: the answer is accepted only if it has exactly one translation per sentence and every protected-name placeholder (Xqax ...) comes back exactly
once. Anything else (an error, a throttle, bad JSON, a lost placeholder) falls back to the fallback translator for that batch, so a Bedrock problem
can make the wording worse but never breaks a passage. Off unless TRANSLATE_MODEL is set; not run against the real service yet (see docs/DEPLOY.md).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional

from translate import add_spanish_marks, plain_register

LOG = logging.getLogger(__name__)
_PLACEHOLDER = re.compile(r"Xq[a-z]+x")
_NAMES = {"en": "English", "es": "Spanish"}
CONTEXT_SENTENCES = 4
MAX_TOKENS = 4000

SYSTEM = (
    "You translate reading passages for school children from {source} to {target}. Rules:\n"
    "1. Translate every sentence faithfully, in simple, natural, grade-appropriate {target}. Never use slang or contractions like gonna or wanna.\n"
    "2. Use the surrounding sentences to resolve ambiguity: keep the gender and number of each person consistent with the passage "
    "(for example Spanish su/sus can mean his, her, their or your: choose what the story means).\n"
    "3. Keep personal names exactly as written (Pedro stays Pedro). Keep numbers as written.\n"
    "4. Tokens like Xqax or Xqbx are protected place names: copy each one exactly, once, where the place belongs in the sentence.\n"
    "5. Return ONLY a JSON array of strings: one translated string per input sentence, same order, same count. Do not merge, split, add or drop sentences."
)


def _prompt(texts: list[str], history: list[tuple[str, str]]) -> str:
    parts = []
    if history:
        parts.append("Context (already translated; do NOT translate again):\n" + "\n".join(f"- {s}" for s, _ in history))
    parts.append("Translate these sentences. JSON array in, JSON array out:\n" + json.dumps(texts, ensure_ascii=False))
    return "\n\n".join(parts)


def _text_of(response: dict[str, Any]) -> str:
    blocks = response["output"]["message"]["content"]
    return "".join(b["text"] for b in blocks if isinstance(b, dict) and "text" in b)


def parse_answer(raw: str, texts: list[str]) -> list[str]:
    """The translations, or ValueError when the answer cannot be trusted (see the module docstring)."""
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("no JSON array in the answer")
    out = json.loads(raw[start:end + 1])
    if not isinstance(out, list) or len(out) != len(texts) or not all(isinstance(t, str) and t.strip() for t in out):
        raise ValueError("the answer is not one non-empty string per sentence")
    for src, got in zip(texts, out):
        if sorted(_PLACEHOLDER.findall(src)) != sorted(_PLACEHOLDER.findall(got)):
            raise ValueError("a protected place name was lost, added or repeated")
        if len(got) > 4 * len(src) + 40:
            raise ValueError("a translation is implausibly long")
    return [t.strip() for t in out]


class BedrockTranslator:
    """Callable like the Opus-MT model. Keeps the last few translated sentences as context for the next batch of the same passage."""

    def __init__(self, client: Any, model_id: str, source: str, target: str, fallback: Optional[Callable[[list[str]], list[str]]] = None) -> None:
        if source not in _NAMES or target not in _NAMES or source == target:
            raise ValueError("Translation is available for en to es or es to en.")
        self._client, self._model_id, self._target, self._fallback = client, model_id, target, fallback
        self._system = SYSTEM.format(source=_NAMES[source], target=_NAMES[target])
        self._history: list[tuple[str, str]] = []
        self.fallbacks = 0  # batches that fell back (shown in the logs; a high number means the prompt or the model needs attention)

    def __call__(self, texts: list[str]) -> list[str]:
        if not texts:
            return []
        try:
            response = self._client.converse(
                modelId=self._model_id, system=[{"text": self._system}],
                messages=[{"role": "user", "content": [{"text": _prompt(texts, self._history)}]}],
                inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": 0},
            )
            out = parse_answer(_text_of(response), texts)
        except Exception as err:  # noqa: BLE001 (throttling, access denied, bad JSON, a lost placeholder: all fall back)
            self.fallbacks += 1
            LOG.warning("Bedrock translation fell back to the built-in translator: %s", err)
            if self._fallback is None:
                raise
            return self._fallback(texts)
        out = [plain_register(t) for t in out] if self._target == "en" else [add_spanish_marks(t) for t in out]
        self._history = (self._history + list(zip(texts, out)))[-CONTEXT_SENTENCES:]
        return out


def from_environment(source: str, target: str, fallback: Callable[[list[str]], list[str]], env: Optional[dict[str, str]] = None,
                     client_factory: Optional[Callable[[str], Any]] = None) -> Callable[[list[str]], list[str]]:
    """The Bedrock translator when TRANSLATE_MODEL=bedrock:<modelId> is set, otherwise the fallback unchanged."""
    import os

    env = os.environ if env is None else env
    value = (env.get("TRANSLATE_MODEL") or "").strip()
    if not value.startswith("bedrock:") or len(value) <= len("bedrock:"):
        return fallback
    if client_factory is None:
        import boto3

        client_factory = lambda region: boto3.client("bedrock-runtime", region_name=region)  # noqa: E731
    try:
        client = client_factory(env.get("TRANSLATE_REGION") or env.get("AWS_REGION") or "us-west-2")
        return BedrockTranslator(client, value.removeprefix("bedrock:"), source, target, fallback)
    except Exception as err:  # noqa: BLE001 (no SDK, no region): keep the built-in translator
        LOG.warning("Bedrock translator not available, using the built-in translator: %s", err)
        return fallback
