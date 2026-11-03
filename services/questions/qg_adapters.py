"""One interface to a language model, three implementations: Ollama (local), Amazon Bedrock Converse (AWS), and a scripted fake for tests.

Every reply carries its token counts, so the real cost of a run is measured and never guessed.
"""
from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_REGION = "us-west-2"


class AdapterError(RuntimeError):
    """A model call failed, or the model returned nothing usable."""


@dataclass(frozen=True)
class ModelReply:
    text: str
    input_tokens: int
    output_tokens: int


class ModelAdapter(Protocol):
    def complete(self, system: str, user: str, *, max_tokens: int = 1500, temperature: float = 0.2) -> ModelReply: ...


def _http_post(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (the host is local or set by the operator)
        return json.loads(response.read())


def _default_think(model: str) -> str | bool | None:
    """gpt-oss takes a level, qwen3 takes on/off, and other models do not take the setting at all."""
    name = model.lower()
    if name.startswith("gpt-oss"):
        return "low"
    if name.startswith("qwen3"):
        return False
    return None


class OllamaAdapter:
    """A model served by a local Ollama (`ollama serve`). Used for development and for repeatable local tests."""

    def __init__(
        self,
        model: str,
        host: str = DEFAULT_OLLAMA_HOST,
        post: Callable[[str, dict[str, Any], float], dict[str, Any]] | None = None,
        think: str | bool | None = "auto",
        timeout: float = 900.0,
    ) -> None:
        self.model, self.host, self._post, self.timeout = model, host.rstrip("/"), post or _http_post, timeout
        self.think = _default_think(model) if think == "auto" else think

    def complete(self, system: str, user: str, *, max_tokens: int = 1500, temperature: float = 0.2) -> ModelReply:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if self.think is not None:
            payload["think"] = self.think  # reasoning models spend tokens thinking; "low" (gpt-oss) or False (qwen3) keeps that small
        try:
            body = self._post(f"{self.host}/api/chat", payload, self.timeout)
        except (OSError, ValueError) as error:
            raise AdapterError(f"Ollama call failed: {error}") from error
        text = (body.get("message") or {}).get("content") or ""
        if not text.strip():
            raise AdapterError("the model returned no final answer (it may have used every token thinking; raise max_tokens)")
        return ModelReply(text, int(body.get("prompt_eval_count") or 0), int(body.get("eval_count") or 0))


def _default_bedrock_client(region: str) -> Any:
    import boto3  # imported here so everything else works without boto3 (it is already in the Lambda runtime)

    return boto3.client("bedrock-runtime", region_name=region)


class BedrockAdapter:
    """A model on Amazon Bedrock, called through the Converse API. Tested here with a fake client only; see docs/QUESTIONS.md for sandbox steps."""

    def __init__(
        self,
        model_id: str,
        region: str = DEFAULT_REGION,
        client: Any | None = None,
        client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.model_id, self.region = model_id, region
        self._client, self._factory = client, client_factory or _default_bedrock_client

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                self._client = self._factory(self.region)
            except ImportError as error:
                raise AdapterError("boto3 is not installed; run `pip install boto3` (it is already present in AWS Lambda)") from error
        return self._client

    def complete(self, system: str, user: str, *, max_tokens: int = 1500, temperature: float = 0.2) -> ModelReply:
        client = self._get_client()
        try:
            response = client.converse(
                modelId=self.model_id,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
            )
        except Exception as error:  # noqa: BLE001 (boto raises many types; every one is reported, none is swallowed)
            raise AdapterError(f"Bedrock call failed: {error}") from error
        blocks = response.get("output", {}).get("message", {}).get("content", [])
        text = "".join(block["text"] for block in blocks if "text" in block)  # reasoning blocks have no "text" key and are skipped
        if not text.strip():
            raise AdapterError("Bedrock returned no text (the model may have used every token reasoning; raise max_tokens)")
        usage = response.get("usage", {})
        return ModelReply(text, int(usage.get("inputTokens", 0)), int(usage.get("outputTokens", 0)))


class FakeAdapter:
    """Replays scripted replies in order and records what it was asked. For tests."""

    def __init__(self, replies: Sequence[str | ModelReply]) -> None:
        self._replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, *, max_tokens: int = 1500, temperature: float = 0.2) -> ModelReply:
        self.calls.append((system, user))
        if not self._replies:
            raise AdapterError("FakeAdapter has no more scripted replies")
        reply = self._replies.pop(0)
        return reply if isinstance(reply, ModelReply) else ModelReply(reply, 0, 0)


def adapter_from_spec(spec: str, region: str = DEFAULT_REGION, client: Any | None = None) -> ModelAdapter:
    """`ollama:<name>` or `bedrock:<modelId>`. Only the first colon splits, because model names contain colons."""
    kind, _, name = spec.partition(":")
    if kind == "ollama" and name:
        return OllamaAdapter(name)
    if kind == "bedrock" and name:
        return BedrockAdapter(name, region=region, client=client)
    raise ValueError(f"unknown model spec {spec!r}; use ollama:<name> or bedrock:<modelId>")
