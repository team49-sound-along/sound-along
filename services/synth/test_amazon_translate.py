import pytest

import amazon_translate as at


class FakeClient:
    def __init__(self, table=None, fail=None):
        self.table, self.fail, self.calls = table or {}, fail or {}, []

    def translate_text(self, **kw):
        self.calls.append(kw)
        err = self.fail.get(kw["Text"])
        if err:
            if isinstance(err, list) and err:
                raise err.pop(0)
            elif not isinstance(err, list):
                raise err
        return {"TranslatedText": self.table.get(kw["Text"], "ES " + kw["Text"])}


def make(client, target="es", **kw):
    return at.AmazonTranslator(client, "en" if target == "es" else "es", target, lambda xs: ["FB " + x for x in xs], clock=lambda: 0.0, sleep=lambda s: None, **kw)


def test_each_sentence_is_one_request_with_the_language_pair_and_the_informal_setting_for_spanish():
    c = FakeClient({"Hello there.": "Hola."})
    out = make(c, formality="informal")(["Hello there.", "Bye."])
    assert out == ["Hola.", "ES Bye."]
    assert c.calls[0] == {"Text": "Hello there.", "SourceLanguageCode": "en", "TargetLanguageCode": "es", "Settings": {"Formality": "INFORMAL"}}


def test_formality_is_only_sent_for_a_target_language_that_accepts_it():
    c = FakeClient()
    make(c, target="en", formality="informal")(["Hola."])
    assert "Settings" not in c.calls[0]


def test_a_failed_or_empty_sentence_uses_the_fallback_and_the_others_keep_amazons_answer():
    c = FakeClient({"A.": "Uno.", "C.": "  "}, fail={"B.": RuntimeError("boom")})
    assert make(c)(["A.", "B.", "C."]) == ["Uno.", "FB B.", "FB C."]


def test_a_lost_protected_name_is_not_accepted():
    c = FakeClient({"We saw Xqax today.": "Vimos hoy."})
    assert make(c)(["We saw Xqax today."]) == ["FB We saw Xqax today."]
    c2 = FakeClient({"We saw Xqax today.": "Vimos Xqax hoy."})
    assert make(c2)(["We saw Xqax today."]) == ["Vimos Xqax hoy."]


def test_a_throttled_request_is_retried_then_succeeds():
    slept = []
    c = FakeClient({"A.": "Uno."}, fail={"A.": [Exception("ThrottlingException: Rate exceeded")]})
    t = at.AmazonTranslator(c, "en", "es", lambda xs: xs, clock=lambda: 0.0, sleep=slept.append)
    assert t(["A."]) == ["Uno."] and len(c.calls) == 2 and 1.0 in slept


def test_a_sentence_too_long_for_one_request_goes_to_the_fallback_without_a_call():
    c = FakeClient()
    assert make(c)(["word " * 2500]) == ["FB " + "word " * 2500]
    assert c.calls == []


@pytest.mark.parametrize("value,expect", [("", False), ("bedrock:x", False), ("amazon", True), ("amazon:informal", True), ("Amazon:Formal", True)])
def test_the_environment_switch(value, expect):
    fb = lambda xs: xs  # noqa: E731
    got = at.from_environment("en", "es", fb, env={"TRANSLATE_MODEL": value}, client_factory=lambda region: FakeClient())
    assert (got is not fb) is expect


def test_an_unavailable_sdk_keeps_the_builtin_translator():
    def boom(region):
        raise RuntimeError("no boto3")
    fb = lambda xs: xs  # noqa: E731
    assert at.from_environment("en", "es", fb, env={"TRANSLATE_MODEL": "amazon"}, client_factory=boom) is fb
