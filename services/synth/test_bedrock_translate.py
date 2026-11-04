"""The Bedrock translator, with a fake Bedrock client. Nothing here calls AWS."""
import json

import pytest

import bedrock_translate as bt
import translate as tr


class FakeClient:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return {"output": {"message": {"content": [{"reasoningContent": {}}, {"text": reply}]}}}


def fallback(texts):
    return ["FALLBACK " + t for t in texts]


class Clock:
    def __init__(self):
        self.t, self.sleeps = 100.0, []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(round(s, 3))
        self.t += s


def make(replies, source="es", target="en", **kw):
    client = FakeClient(replies)
    clock = Clock()
    model = bt.BedrockTranslator(client, "example.model-v1:0", source, target, fallback, clock=clock.now, sleep=clock.sleep, **kw)
    model.clock = clock
    return client, model


def test_a_good_answer_is_returned_and_the_request_asks_for_one_string_per_sentence_with_temperature_zero():
    client, model = make([json.dumps(["Ana and her brother go to the park.", "Their bus broke down."])])
    out = model(["Ana y su hermano van al parque.", "Su autobús se rompió."])
    assert out == ["Ana and her brother go to the park.", "Their bus broke down."]
    call = client.calls[0]
    assert call["modelId"] == "example.model-v1:0" and call["inferenceConfig"]["temperature"] == 0
    assert "Spanish to English" in call["system"][0]["text"] or "from Spanish to English" in call["system"][0]["text"]
    assert "Ana y su hermano van al parque." in call["messages"][0]["content"][0]["text"]


def test_the_previous_sentences_are_sent_as_context_with_the_next_batch():
    client, model = make([json.dumps(["One."]), json.dumps(["Two."])])
    model(["Uno."])
    model(["Dos."])
    assert "Uno." in client.calls[1]["messages"][0]["content"][0]["text"] and "Context" in client.calls[1]["messages"][0]["content"][0]["text"]


def test_text_around_the_json_array_is_ignored_but_a_wrong_count_falls_back():
    _, model = make(["Here you go:\n" + json.dumps(["Hello."]) + "\nDone."])
    assert model(["Hola."]) == ["Hello."]
    _, model = make([json.dumps(["Only one."])])
    assert model(["Uno.", "Dos."]) == ["FALLBACK Uno.", "FALLBACK Dos."] and model.fallbacks == 1


@pytest.mark.parametrize("answer", ["not json at all", json.dumps({"a": 1}), json.dumps([""]), json.dumps([5])])
def test_unusable_answers_fall_back(answer):
    _, model = make([answer])
    assert model(["Hola."]) == ["FALLBACK Hola."]


def test_a_lost_or_repeated_placeholder_falls_back_so_a_place_name_is_never_dropped():
    _, model = make([json.dumps(["We saw it."])])
    assert model(["Vimos Xqax."]) == ["FALLBACK Vimos Xqax."]
    _, model = make([json.dumps(["We saw Xqax and Xqax."])])
    assert model(["Vimos Xqax."]) == ["FALLBACK Vimos Xqax."]
    _, model = make([json.dumps(["We saw Xqax."])])
    assert model(["Vimos Xqax."]) == ["We saw Xqax."]


def test_errors_such_as_throttling_fall_back_and_never_reach_the_caller():
    _, model = make([RuntimeError("ThrottlingException")])
    assert model(["Hola."]) == ["FALLBACK Hola."]


def test_without_a_fallback_the_error_is_raised():
    client = FakeClient([RuntimeError("boom")])
    with pytest.raises(RuntimeError):
        bt.BedrockTranslator(client, "m", "es", "en")(["Hola."])


def test_casual_english_is_written_out_in_full_for_spanish_to_english_only():
    _, model = make([json.dumps(["They are gonna eat."])])
    assert model(["Van a comer."]) == ["They are going to eat."]


def test_only_english_and_spanish_are_accepted():
    with pytest.raises(ValueError):
        bt.BedrockTranslator(FakeClient([]), "m", "en", "fr")
    with pytest.raises(ValueError):
        bt.BedrockTranslator(FakeClient([]), "m", "en", "en")


def test_environment_selects_the_translator_and_never_touches_aws_when_it_is_off(monkeypatch):
    def boom(region):
        raise AssertionError("must not create a client")

    assert bt.from_environment("es", "en", fallback, env={}, client_factory=boom) is fallback
    assert bt.from_environment("es", "en", fallback, env={"TRANSLATE_MODEL": "bedrock:"}, client_factory=boom) is fallback
    assert bt.from_environment("es", "en", fallback, env={"TRANSLATE_MODEL": "other:x"}, client_factory=boom) is fallback
    seen = {}
    model = bt.from_environment("es", "en", fallback, env={"TRANSLATE_MODEL": "bedrock:example.model-v1:0", "TRANSLATE_REGION": "us-west-2"},
                                client_factory=lambda region: seen.setdefault("region", region) and FakeClient([json.dumps(["Hi."])]))
    assert isinstance(model, bt.BedrockTranslator) and seen["region"] == "us-west-2" and model(["Hola."]) == ["Hi."]


def test_a_client_that_cannot_be_created_keeps_the_builtin_translator():
    def broken(region):
        raise RuntimeError("no sdk")

    assert bt.from_environment("es", "en", fallback, env={"TRANSLATE_MODEL": "bedrock:m"}, client_factory=broken) is fallback


def test_it_works_inside_translate_passage_so_the_sentence_map_is_unchanged():
    _, model = make([json.dumps(["Ana and her brother go to the park.", "Their bus broke down."])])
    out = tr.translate_passage({"title": "", "content": "<p>Ana y su hermano van al parque. Su autobús se rompió.</p>"}, model, names_fn=lambda t: [])
    assert out.sentence_map == [[0], [1]] and "her brother" in out.content_html


def test_requests_are_never_closer_together_than_the_minimum_interval():
    _, model = make([json.dumps(["A."]), json.dumps(["B."]), json.dumps(["C."])], min_interval=1.1)
    model(["a."]); model(["b."]); model(["c."])
    assert model.clock.sleeps == [1.1, 1.1], "the first call is immediate, each later one waits out the interval"


def test_a_pause_that_already_passed_is_not_waited_twice():
    _, model = make([json.dumps(["A."]), json.dumps(["B."])], min_interval=1.1)
    model(["a."])
    model.clock.t += 5
    model(["b."])
    assert model.clock.sleeps == []


def test_a_throttled_request_is_retried_after_a_pause_and_then_succeeds():
    _, model = make([RuntimeError("ThrottlingException: Too many requests"), json.dumps(["Hi."])], min_interval=1.1)
    assert model(["Hola."]) == ["Hi."]
    assert 2.0 in model.clock.sleeps and model.fallbacks == 0


def test_a_request_that_stays_throttled_falls_back_after_the_retries():
    errors = [RuntimeError("ThrottlingException")] * (bt.THROTTLE_RETRIES + 1)
    client, model = make(errors, min_interval=0)
    assert model(["Hola."]) == ["FALLBACK Hola."] and len(client.calls) == bt.THROTTLE_RETRIES + 1


def test_other_errors_are_not_retried():
    client, model = make([RuntimeError("AccessDeniedException")], min_interval=0)
    assert model(["Hola."]) == ["FALLBACK Hola."] and len(client.calls) == 1


def test_the_interval_comes_from_the_environment_and_a_bad_value_means_the_default():
    for value, expected in (("2.2", 2.2), ("0", 0.0), ("", bt.DEFAULT_MIN_INTERVAL), ("abc", bt.DEFAULT_MIN_INTERVAL), ("-1", bt.DEFAULT_MIN_INTERVAL), ("999", bt.DEFAULT_MIN_INTERVAL)):
        assert bt._interval(value) == expected
    model = bt.from_environment("es", "en", fallback, env={"TRANSLATE_MODEL": "bedrock:m", "TRANSLATE_MIN_INTERVAL": "2.2"}, client_factory=lambda region: FakeClient([]))
    assert model._min_interval == 2.2
