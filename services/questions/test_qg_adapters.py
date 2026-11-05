"""Model adapters. Ollama is tested with a fake HTTP post; Bedrock with a fake client. No network anywhere."""
import json

import pytest

from qg_adapters import AdapterError, BedrockAdapter, FakeAdapter, ModelReply, OllamaAdapter, adapter_from_spec


# ---- Ollama --------------------------------------------------------------------------------------------------------
def ollama_post(response, seen):
    def post(url, payload, timeout):
        seen.append((url, payload, timeout))
        return response
    return post


def test_ollama_request_shape_and_token_counts():
    seen = []
    reply = {"message": {"content": '{"ok": true}', "thinking": "reasoning"}, "prompt_eval_count": 120, "eval_count": 45}
    adapter = OllamaAdapter("gpt-oss:20b", post=ollama_post(reply, seen))
    result = adapter.complete("system text", "user text", max_tokens=900, temperature=0.1)
    url, payload, _ = seen[0]
    assert url == "http://127.0.0.1:11434/api/chat"
    assert payload["model"] == "gpt-oss:20b" and payload["stream"] is False
    assert payload["messages"] == [{"role": "system", "content": "system text"}, {"role": "user", "content": "user text"}]
    assert payload["options"] == {"temperature": 0.1, "num_predict": 900}
    assert payload["think"] == "low"
    assert result == ModelReply('{"ok": true}', 120, 45)


def test_ollama_reasoning_only_reply_is_an_error_with_a_clear_message():
    reply = {"message": {"content": "", "thinking": "still thinking"}, "prompt_eval_count": 10, "eval_count": 900}
    adapter = OllamaAdapter("gpt-oss:20b", post=ollama_post(reply, []))
    with pytest.raises(AdapterError, match="max_tokens"):
        adapter.complete("s", "u")


def test_ollama_transport_failure_becomes_an_adapter_error():
    def boom(url, payload, timeout):
        raise OSError("connection refused")
    with pytest.raises(AdapterError, match="connection refused"):
        OllamaAdapter("m", post=boom).complete("s", "u")


# ---- Bedrock -------------------------------------------------------------------------------------------------------
class FakeBedrockClient:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def bedrock_response():
    return {
        "output": {"message": {"content": [{"reasoningContent": {"reasoningText": {"text": "hidden"}}}, {"text": '{"questions": []}'}]}},
        "usage": {"inputTokens": 321, "outputTokens": 64},
    }


def test_bedrock_uses_converse_with_system_and_inference_config():
    client = FakeBedrockClient(bedrock_response())
    adapter = BedrockAdapter("openai.gpt-oss-20b-1:0", client=client)
    result = adapter.complete("sys", "usr", max_tokens=700, temperature=0.2)
    call = client.calls[0]
    assert call["modelId"] == "openai.gpt-oss-20b-1:0"
    assert call["system"] == [{"text": "sys"}]
    assert call["messages"] == [{"role": "user", "content": [{"text": "usr"}]}]
    assert call["inferenceConfig"] == {"maxTokens": 700, "temperature": 0.2}
    assert result == ModelReply('{"questions": []}', 321, 64)  # the reasoning block is skipped, only text is returned


def test_bedrock_errors_are_wrapped_not_swallowed():
    adapter = BedrockAdapter("m", client=FakeBedrockClient(error=RuntimeError("AccessDeniedException")))
    with pytest.raises(AdapterError, match="AccessDeniedException"):
        adapter.complete("s", "u")


def test_bedrock_without_boto3_explains_what_to_do():
    def no_boto3(region):
        raise ImportError("No module named boto3")
    with pytest.raises(AdapterError, match="boto3"):
        BedrockAdapter("m", client_factory=no_boto3).complete("s", "u")


def test_bedrock_reply_with_no_text_is_an_error():
    response = {"output": {"message": {"content": [{"reasoningContent": {}}]}}, "usage": {"inputTokens": 1, "outputTokens": 1}}
    with pytest.raises(AdapterError, match="no text"):
        BedrockAdapter("m", client=FakeBedrockClient(response)).complete("s", "u")


# ---- fake + spec ---------------------------------------------------------------------------------------------------
def test_fake_adapter_replays_in_order_and_records_calls():
    fake = FakeAdapter(["one", ModelReply("two", 5, 6)])
    assert fake.complete("s1", "u1").text == "one"
    assert fake.complete("s2", "u2") == ModelReply("two", 5, 6)
    assert fake.calls == [("s1", "u1"), ("s2", "u2")]
    with pytest.raises(AdapterError, match="no more"):
        fake.complete("s", "u")


def test_adapter_from_spec_splits_on_the_first_colon_only():
    local = adapter_from_spec("ollama:gpt-oss:20b")
    assert isinstance(local, OllamaAdapter) and local.model == "gpt-oss:20b"
    aws = adapter_from_spec("bedrock:openai.gpt-oss-20b-1:0", region="us-west-2", client=FakeBedrockClient())
    assert isinstance(aws, BedrockAdapter) and aws.model_id == "openai.gpt-oss-20b-1:0"
    with pytest.raises(ValueError):
        adapter_from_spec("openai:gpt")


# ---- the `think` setting depends on the model ----------------------------------------------------------------------
def think_for(model, **kwargs):
    seen = []
    reply = {"message": {"content": "ok"}, "prompt_eval_count": 1, "eval_count": 1}
    OllamaAdapter(model, post=ollama_post(reply, seen), **kwargs).complete("s", "u")
    return seen[0][1]


def test_think_is_low_for_gpt_oss_off_for_qwen3_and_absent_for_other_models():
    assert think_for("gpt-oss:20b")["think"] == "low"
    assert think_for("qwen3:30b")["think"] is False
    assert "think" not in think_for("llama3.2:latest")


def test_think_can_be_set_explicitly_or_removed():
    assert think_for("gpt-oss:20b", think="high")["think"] == "high"
    assert "think" not in think_for("gpt-oss:20b", think=None)


# ---- Bedrock: schema mode, output cap and the 1-request-per-second pause --------------------------------------------
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}


def tool_response(payload):
    return {"output": {"message": {"content": [{"toolUse": {"toolUseId": "t1", "name": "reply", "input": payload}}]}}, "usage": {"inputTokens": 40, "outputTokens": 9}}


def test_nova_uses_a_forced_tool_schema_and_returns_the_tool_input_as_json_text():
    client = FakeBedrockClient(tool_response({"answer": "B"}))
    result = BedrockAdapter("us.amazon.nova-lite-v1:0", client=client, sleep=lambda s: None).complete("s", "u", json_schema=SCHEMA)
    config = client.calls[0]["toolConfig"]
    assert config["tools"][0]["toolSpec"]["inputSchema"] == {"json": SCHEMA}
    assert config["toolChoice"] == {"any": {}}
    assert json.loads(result.text) == {"answer": "B"} and (result.input_tokens, result.output_tokens) == (40, 9)


def test_models_without_schema_mode_get_no_tool_config():
    client = FakeBedrockClient(bedrock_response())
    BedrockAdapter("us.meta.llama4-maverick-17b-instruct-v1:0", client=client, sleep=lambda s: None).complete("s", "u", json_schema=SCHEMA)
    assert "toolConfig" not in client.calls[0]


def test_schema_mode_can_be_switched_off_for_a_comparison():
    client = FakeBedrockClient(bedrock_response())
    BedrockAdapter("us.amazon.nova-lite-v1:0", client=client, use_schema=False, sleep=lambda s: None).complete("s", "u", json_schema=SCHEMA)
    assert "toolConfig" not in client.calls[0]


def test_max_tokens_is_capped_for_models_with_a_small_output_limit():
    client = FakeBedrockClient(bedrock_response())
    BedrockAdapter("us.amazon.nova-lite-v1:0", client=client, sleep=lambda s: None).complete("s", "u", max_tokens=3000)
    assert client.calls[0]["inferenceConfig"]["maxTokens"] == 2048


def test_calls_are_spaced_at_least_a_second_apart():
    now, slept = [100.0], []
    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds
    adapter = BedrockAdapter("m", client=FakeBedrockClient(bedrock_response()), min_interval=1.1, clock=lambda: now[0], sleep=sleep)
    adapter.complete("s", "u")  # first call: no wait
    now[0] += 0.3
    adapter.complete("s", "u")  # 0.3 s later: waits the other 0.8 s
    now[0] += 5
    adapter.complete("s", "u")  # long gap: no wait
    assert slept == [pytest.approx(0.8)]


def test_ollama_and_fake_accept_and_ignore_a_schema():
    reply = {"message": {"content": "ok"}, "prompt_eval_count": 1, "eval_count": 1}
    assert OllamaAdapter("m", post=ollama_post(reply, [])).complete("s", "u", json_schema=SCHEMA).text == "ok"
    assert FakeAdapter(["x"]).complete("s", "u", json_schema=SCHEMA).text == "x"
