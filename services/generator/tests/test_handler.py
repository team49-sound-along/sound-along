import json
from decimal import Decimal

import pytest

import handler as h
from clients import Clients
from fakes import EVENT, JOB_ID, PASSAGE_ID, FakeEngine, FakeS3, FakeTable, fake_encoder, raw_passage

BUCKET = "test-bucket"


def make_deps(s3: FakeS3, table: FakeTable, engine_factory=FakeEngine) -> h.Dependencies:
    return h.Dependencies(Clients(s3=s3, table=table, bucket=BUCKET), engine_factory, fake_encoder)


@pytest.fixture
def world():
    s3 = FakeS3({EVENT["rawKey"]: raw_passage()})
    return s3, FakeTable()


def test_success_uploads_objects_with_content_types(world):
    s3, table = world
    result = h.process(EVENT, make_deps(s3, table))
    assert result == {"status": "done", "jobId": JOB_ID, "passageId": PASSAGE_ID}
    assert s3.content_types[f"data/{PASSAGE_ID}.mp3"] == "audio/mpeg"
    assert s3.content_types[f"data/{PASSAGE_ID}.timing.json"] == "application/json"
    timing = json.loads(s3.objects[f"data/{PASSAGE_ID}.timing.json"])
    assert timing["id"] == PASSAGE_ID and timing["title"] == "The Park"
    assert timing["engine"] == "fake" and timing["voice"] == "fake_voice"
    assert [w["text"] for w in timing["words"]][:3] == ["We", "went", "to"]


def test_job_steps_in_order_and_final_state(world):
    s3, table = world
    h.process(EVENT, make_deps(s3, table))
    assert table.steps(JOB_ID) == ["parse", "synthesize", "align", "publish", "done"]
    job = table.job(JOB_ID)
    assert job["status"] == "done" and job["step"] == "done" and job["error"] is None
    assert job["passageId"] == PASSAGE_ID
    assert job["finishedAt"].endswith("Z")
    assert job["metrics"]["words"] == 8 and isinstance(job["metrics"]["audioSeconds"], Decimal)
    assert job["ttl"] > 0


def test_passage_summary_matches_catalog_contract(world):
    s3, table = world
    h.process(EVENT, make_deps(s3, table))
    item = table.items[("PASSAGE", PASSAGE_ID)]
    timing = json.loads(s3.objects[f"data/{PASSAGE_ID}.timing.json"])
    expected_keys = {"pk", "sk", "id", "title", "words", "durationMs", "engine", "voice", "createdAt", "source", "vocabCount", "metrics"}
    assert set(item) == expected_keys
    assert item["id"] == PASSAGE_ID and item["title"] == "The Park"
    assert item["words"] == timing["metrics"]["words"] == 8
    assert item["durationMs"] == timing["duration_ms"]
    assert item["source"] == "generated" and item["vocabCount"] == 0
    assert item["engine"] == "fake" and item["voice"] == "fake_voice"
    assert item["createdAt"].endswith("Z") and "T" in item["createdAt"]
    assert item["metrics"]["characters"] == timing["metrics"]["characters"]


def test_failure_marks_job_failed_and_returns_normally():
    s3, table = FakeS3(), FakeTable()  # raw object missing
    result = h.process(EVENT, make_deps(s3, table))
    job = table.job(JOB_ID)
    assert result["status"] == "failed"
    assert job["status"] == "failed" and job["error"] == h.FRIENDLY_ERROR
    assert job["finishedAt"]
    assert not s3.content_types and ("PASSAGE", PASSAGE_ID) not in table.items


def test_engine_failure_is_handled(world):
    s3, table = world

    def broken() -> None:
        raise RuntimeError("model missing")

    assert h.process(EVENT, make_deps(s3, table, broken))["status"] == "failed"
    assert table.job(JOB_ID)["error"] == h.FRIENDLY_ERROR


def test_empty_passage_fails_cleanly():
    s3, table = FakeS3({EVENT["rawKey"]: raw_passage(content="<p></p>")}), FakeTable()
    assert h.process(EVENT, make_deps(s3, table))["status"] == "failed"


def test_handler_without_env_returns_normally(monkeypatch):
    monkeypatch.delenv("BUCKET", raising=False)
    monkeypatch.delenv("TABLE_NAME", raising=False)
    assert h.handler(EVENT, None)["status"] == "failed"
