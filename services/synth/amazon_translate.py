"""Amazon Translate in front of the built-in Opus-MT translator (optional, off unless TRANSLATE_MODEL=amazon or amazon:informal).

Why: a managed translation service with no model to host, and for Spanish a Formality setting (INFORMAL gives "tú", which suits children's text; the
built-in model mixes "tú" and "usted"). Same shape as the other translators (a function from a list of sentences to a list of sentences), so
`translate_passage`, the sentence map and the language switch do not change.

Safety, as for the Bedrock translator: a sentence whose protected-name placeholders (Xqax ...) do not all come back exactly once, or whose request
fails (throttle, error, empty answer), is translated by the fallback instead. A service problem can make wording worse but never breaks a passage.
Not run against the real service yet (no AWS credentials here); the request shape follows the TranslateText API (docs/DEPLOY.md).

Cost: about USD 15 per million characters; a 1,000-word passage is about 6,000 characters, so under USD 0.10.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable, Optional

from translate import add_spanish_marks, plain_register

LOG = logging.getLogger(__name__)
_PLACEHOLDER = re.compile(r"Xq[a-z]+x")
MAX_BYTES = 9_000  # TranslateText accepts up to 10,000 bytes of UTF-8 per request
MIN_INTERVAL = 0.06  # seconds between requests: the default quota is far above this, the pause only smooths bursts
RETRIES = 3
_THROTTLE = re.compile(r"throttl|too ?many ?requests|rate exceeded|limit exceeded", re.I)
FORMALITY = {"informal": "INFORMAL", "formal": "FORMAL"}
FORMALITY_LANGUAGES = {"es"}  # the target languages that accept the Formality setting among the two we translate to


class AmazonTranslator:
    def __init__(self, client: Any, source: str, target: str, fallback: Callable[[list[str]], list[str]], formality: Optional[str] = None,
                 min_interval: float = MIN_INTERVAL, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
        self._client, self._source, self._target, self._fallback = client, source, target, fallback
        self._formality = FORMALITY.get((formality or "").lower()) if target in FORMALITY_LANGUAGES else None
        self._min_interval, self._clock, self._sleep = min_interval, clock, sleep
        self._last = -1e9

    def _wait(self) -> None:
        gap = self._min_interval - (self._clock() - self._last)
        if gap > 0:
            self._sleep(gap)
        self._last = self._clock()

    def _one(self, text: str) -> str:
        if len(text.encode("utf-8")) > MAX_BYTES:
            raise ValueError("sentence too long for one request")
        params: dict[str, Any] = {"Text": text, "SourceLanguageCode": self._source, "TargetLanguageCode": self._target}
        if self._formality:
            params["Settings"] = {"Formality": self._formality}
        for attempt in range(RETRIES + 1):
            self._wait()
            try:
                answer = self._client.translate_text(**params)["TranslatedText"]
                if not isinstance(answer, str) or not answer.strip():
                    raise ValueError("empty translation")
                return answer
            except Exception as err:  # noqa: BLE001
                if attempt < RETRIES and _THROTTLE.search(f"{type(err).__name__} {err}"):
                    self._sleep(1.0 * (attempt + 1))
                    continue
                raise
        raise RuntimeError("unreachable")

    def __call__(self, texts: list[str]) -> list[str]:
        out: list[Optional[str]] = [None] * len(texts)
        redo: list[int] = []
        for i, text in enumerate(texts):
            try:
                got = self._one(text)
                if any(got.count(p) != 1 for p in _PLACEHOLDER.findall(text)):
                    raise ValueError("a protected name was lost")
                out[i] = got
            except Exception as err:  # noqa: BLE001 (this sentence goes to the fallback)
                LOG.warning("Amazon Translate failed for one sentence, using the built-in translator: %s", err)
                redo.append(i)
        if redo:
            fallback = self._fallback([texts[i] for i in redo])
            for i, got in zip(redo, fallback):
                out[i] = got
        done = [o or "" for o in out]
        return [add_spanish_marks(t) for t in done] if self._target == "es" else [plain_register(t) for t in done]


def from_environment(source: str, target: str, fallback: Callable[[list[str]], list[str]], env: Optional[dict[str, str]] = None,
                     client_factory: Optional[Callable[[str], Any]] = None) -> Callable[[list[str]], list[str]]:
    """Amazon Translate when TRANSLATE_MODEL is `amazon` or `amazon:informal` / `amazon:formal`, otherwise the fallback unchanged."""
    import os

    env = os.environ if env is None else env
    value = (env.get("TRANSLATE_MODEL") or "").strip().lower()
    if value != "amazon" and not value.startswith("amazon:"):
        return fallback
    formality = value.partition(":")[2] or None
    if formality and formality not in FORMALITY:
        LOG.warning("Unknown formality %r for Amazon Translate, ignoring it", formality)
        formality = None
    try:
        if client_factory is None:
            import boto3

            client_factory = lambda region: boto3.client("translate", region_name=region)  # noqa: E731
        client = client_factory(env.get("TRANSLATE_REGION") or env.get("AWS_REGION") or "us-west-2")
        return AmazonTranslator(client, source, target, fallback, formality=formality)
    except Exception as err:  # noqa: BLE001 (no SDK, no region): keep the built-in translator
        LOG.warning("Amazon Translate not available, using the built-in translator: %s", err)
        return fallback
