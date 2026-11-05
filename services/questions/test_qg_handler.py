"""The Lambda handler, tested with a fake S3 and a pretend model. It must never write anything under data/ (that prefix is served)."""
import gzip
import json

import pytest

from conftest import PretendModel, make_timing
from qg_adapters import FakeAdapter, ModelReply
from qg_handler import handle

GOOD = {"skill": "literal", "question": "Where is Piedmont Park?", "choices": ["In Atlanta, Georgia.", "In a small town.", "Far from any city."], "answerIndex": 0, "evidenceSentence": 2}
TRUTH = {"Where is Piedmont Park?": "In Atlanta, Georgia."}
ENV = {"QUESTIONS_ENABLED": "true", "QUESTIONS_MODEL": "bedrock:test-model", "BUCKET": "b"}


class Missing(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


class FakeS3:
    def __init__(self, objects):
        self.objects, self.puts = dict(objects), []

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise Missing(Key)
        body = self.objects[Key]

        class Body:
            def read(self_inner):
                return body
        return {"Body": Body()}

    def put_object(self, **kwargs):
        self.puts.append(kwargs)


def timing_bytes(gzipped=True):
    raw = json.dumps(make_timing()).encode()
    return gzip.compress(raw) if gzipped else raw


def model():
    return PretendModel(ModelReply(json.dumps({"questions": [GOOD]}), 900, 400), TRUTH)


def run(s3, env=ENV, event=None, adapter=None):
    return handle(event or {"passageId": "p-1"}, s3=s3, bucket="b", env=env, adapter_factory=lambda spec, region: adapter or model(), today="2026-11-03")


def test_it_drafts_into_raw_and_never_under_data():
    s3 = FakeS3({"data/p-1.timing.json": timing_bytes()})
    result = run(s3)
    assert result["status"] == "drafted" and result["kept"] == 1 and result["dropped"] == 0
    assert [p["Key"] for p in s3.puts] == ["raw/questions/p-1.draft.json"]
    assert s3.puts[0]["ContentType"] == "application/json" and s3.puts[0]["Bucket"] == "b"
    draft = json.loads(s3.puts[0]["Body"])
    assert draft["status"] == "draft" and draft["passageId"] == "p-1"
    assert not any(p["Key"].startswith("data/") for p in s3.puts)


def test_a_plain_json_timing_file_also_works():
    s3 = FakeS3({"data/p-1.timing.json": timing_bytes(gzipped=False)})
    assert run(s3)["status"] == "drafted"


def test_the_kill_switch_does_nothing_and_calls_no_model():
    s3, adapter = FakeS3({"data/p-1.timing.json": timing_bytes()}), FakeAdapter([])
    assert run(s3, env={**ENV, "QUESTIONS_ENABLED": "false"}, adapter=adapter)["status"] == "disabled"
    assert s3.puts == [] and adapter.calls == []


def test_a_reviewed_questions_file_is_never_replaced():
    reviewed = json.dumps({"reviewed": True, "questions": []}).encode()
    s3, adapter = FakeS3({"data/p-1.timing.json": timing_bytes(), "data/p-1.questions.json": reviewed}), FakeAdapter([])
    result = run(s3, adapter=adapter)
    assert result["status"] == "skipped" and s3.puts == [] and adapter.calls == []


def test_an_unsafe_passage_id_is_rejected():
    with pytest.raises(ValueError):
        run(FakeS3({}), event={"passageId": "../secrets"})
    with pytest.raises(ValueError):
        run(FakeS3({}), event={"other": 1})


def test_a_missing_model_setting_is_a_clear_error():
    with pytest.raises(ValueError, match="QUESTIONS_MODEL"):
        run(FakeS3({"data/p-1.timing.json": timing_bytes()}), env={"QUESTIONS_ENABLED": "true"})


def test_failures_are_reported_not_raised_and_write_nothing():
    s3 = FakeS3({"data/p-1.timing.json": timing_bytes()})
    result = run(s3, adapter=FakeAdapter([ModelReply("sorry I cannot", 5, 2)]))
    assert result["status"] == "failed" and "JSON" in result["error"] and s3.puts == []
    assert run(FakeS3({}))["status"] == "failed"  # the timing file does not exist yet


def test_min_interval_setting_reaches_the_bedrock_adapter():
    from qg_adapters import BedrockAdapter, adapter_from_spec
    assert adapter_from_spec("bedrock:amazon.nova-lite-v1:0", client=object(), min_interval=2.2)._min_interval == 2.2
    assert adapter_from_spec("bedrock:amazon.nova-lite-v1:0", client=object())._min_interval == 1.1
    assert isinstance(adapter_from_spec("bedrock:m", client=object(), min_interval=0), BedrockAdapter)


def test_a_bad_min_interval_is_a_loud_configuration_error():
    import pytest
    from qg_handler import _min_interval
    assert _min_interval({}) is None and _min_interval({"QUESTIONS_MIN_INTERVAL": "2.2"}) == 2.2
    for bad in ("fast", "-1", "99"):
        with pytest.raises(ValueError, match="QUESTIONS_MIN_INTERVAL"):
            _min_interval({"QUESTIONS_MIN_INTERVAL": bad})
