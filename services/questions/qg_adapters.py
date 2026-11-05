"""One interface to a language model, three implementations: Ollama (local), Amazon Bedrock Converse (AWS), and a scripted fake for tests.

Every reply carries its token counts, so the real cost of a run is measured and never guessed.
"""
from __future__ import annotations

import json
import time
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
    def complete(
        self, system: str, user: str, *, max_tokens: int = 1500, temperature: float = 0.2, json_schema: dict[str, Any] | None = None
    ) -> ModelReply: ...


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

    def complete(
        self, system: str, user: str, *, max_tokens: int = 1500, temperature: float = 0.2, json_schema: dict[str, Any] | None = None
    ) -> ModelReply:  # json_schema is ignored: local models are only asked in words
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


SCHEMA_TOOL = "reply"
MIN_SECONDS_BETWEEN_CALLS = 1.1  # the hackathon limit is 1 request per second; the margin covers clock jitter


def _is_nova(model_id: str) -> bool:
    return "amazon.nova" in model_id.lower()


class BedrockAdapter:
    """A model on Amazon Bedrock, called through the Converse API. Tested here with a fake client only; see docs/QUESTIONS.md for sandbox steps.

    Three behaviours depend on the model or the hackathon rules:
    - Amazon Nova can be forced to answer in a JSON Schema by describing the answer as a tool (AWS calls this constrained decoding). `use_schema` is on for Nova.
    - Nova has a small output limit, so `max_output_tokens` caps every request (2048 for Nova).
    - Calls are spaced `min_interval` seconds apart (the hackathon allows 1 request per second).
    """

    def __init__(
        self,
        model_id: str,
        region: str = DEFAULT_REGION,
        client: Any | None = None,
        client_factory: Callable[[str], Any] | None = None,
        use_schema: bool | None = None,
        max_output_tokens: int | None = None,
        min_interval: float = MIN_SECONDS_BETWEEN_CALLS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model_id, self.region = model_id, region
        self._client, self._factory = client, client_factory or _default_bedrock_client
        self.use_schema = _is_nova(model_id) if use_schema is None else use_schema
        self.max_output_tokens = (2048 if _is_nova(model_id) else None) if max_output_tokens is None else max_output_tokens
        self._min_interval, self._clock, self._sleep = min_interval, clock, sleep
        self._last_call: float | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                self._client = self._factory(self.region)
            except ImportError as error:
                raise AdapterError("boto3 is not installed; run `pip install boto3` (it is already present in AWS Lambda)") from error
        return self._client

    def _wait_for_turn(self) -> None:
        if self._last_call is not None:
            remaining = self._min_interval - (self._clock() - self._last_call)
            if remaining > 0:
                self._sleep(remaining)
        self._last_call = self._clock()

    def complete(
        self, system: str, user: str, *, max_tokens: int = 1500, temperature: float = 0.2, json_schema: dict[str, Any] | None = None
    ) -> ModelReply:
        client = self._get_client()
        cap = min(max_tokens, self.max_output_tokens) if self.max_output_tokens else max_tokens
        request: dict[str, Any] = {
            "modelId": self.model_id,
            "system": [{"text": system}],
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "inferenceConfig": {"maxTokens": cap, "temperature": temperature},
        }
        if json_schema is not None and self.use_schema:
            request["toolConfig"] = {
                "tools": [{"toolSpec": {"name": SCHEMA_TOOL, "description": "Return the answer in this exact structure.", "inputSchema": {"json": json_schema}}}],
                "toolChoice": {"any": {}},
            }
        self._wait_for_turn()
        try:
            response = client.converse(**request)
        except Exception as error:  # noqa: BLE001 (boto raises many types; every one is reported, none is swallowed)
            raise AdapterError(f"Bedrock call failed: {error}") from error
        blocks = response.get("output", {}).get("message", {}).get("content", [])
        text = "".join(block["text"] for block in blocks if "text" in block)  # reasoning blocks have no "text" key and are skipped
        if not text.strip():
            tool = next((block["toolUse"] for block in blocks if "toolUse" in block), None)
            if tool is not None:
                text = json.dumps(tool.get("input", {}))  # schema mode: the structured answer arrives as the tool's input
        if not text.strip():
            raise AdapterError("Bedrock returned no text (the model may have used every token reasoning; raise max_tokens)")
        usage = response.get("usage", {})
        return ModelReply(text, int(usage.get("inputTokens", 0)), int(usage.get("outputTokens", 0)))


class FakeAdapter:
    """Replays scripted replies in order and records what it was asked. For tests."""

    def __init__(self, replies: Sequence[str | ModelReply]) -> None:
        self._replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(
        self, system: str, user: str, *, max_tokens: int = 1500, temperature: float = 0.2, json_schema: dict[str, Any] | None = None
    ) -> ModelReply:
        self.calls.append((system, user))
        if not self._replies:
            raise AdapterError("FakeAdapter has no more scripted replies")
        reply = self._replies.pop(0)
        return reply if isinstance(reply, ModelReply) else ModelReply(reply, 0, 0)


def adapter_from_spec(spec: str, region: str = DEFAULT_REGION, client: Any | None = None, min_interval: float | None = None) -> ModelAdapter:
    """`ollama:<name>` or `bedrock:<modelId>`. Only the first colon splits, because model names contain colons."""
    kind, _, name = spec.partition(":")
    if kind == "ollama" and name:
        return OllamaAdapter(name)
    if kind == "bedrock" and name:
        return BedrockAdapter(name, region=region, client=client, min_interval=MIN_SECONDS_BETWEEN_CALLS if min_interval is None else min_interval)
    raise ValueError(f"unknown model spec {spec!r}; use ollama:<name> or bedrock:<modelId>")
