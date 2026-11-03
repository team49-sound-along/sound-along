import gzip
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
    timing = json.loads(gzip.decompress(s3.objects[f"data/{PASSAGE_ID}.timing.json"]))
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
    timing = json.loads(gzip.decompress(s3.objects[f"data/{PASSAGE_ID}.timing.json"]))
    expected_keys = {"pk", "sk", "id", "title", "words", "durationMs", "engine", "voice", "createdAt", "source", "vocabCount", "language", "metrics"}
    assert set(item) == expected_keys
    assert item["id"] == PASSAGE_ID and item["title"] == "The Park"
    assert item["words"] == timing["metrics"]["words"] == 8
    assert item["durationMs"] == timing["duration_ms"]
    assert item["source"] == "generated" and item["vocabCount"] == 0 and item["language"] == "en"
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


# --- v2: settings, pronunciations, recordings, review --------------------------------------------------------------

import numpy as np

from asr_words import Heard

HUMAN_ID = "33333333-3333-3333-3333-333333333333"


def raw_v2(**extra) -> bytes:
    base = {"uuid": "x", "title": "The Park", "content": "<p>We went to the park. It was fun.</p>", "source": "generated",
            "settings": {"voice": "af_bella", "speed": 1.0, "mp3Kbps": 32}, "pronunciations": {"park": "pahrk"},
            "qualityCheck": True}
    return json.dumps({**base, **extra}).encode()


def v2_deps(s3, table, spoken):
    deps = make_deps(s3, table)
    return h.Dependencies(deps.clients, deps.engine_factory, fake_encoder, lambda audio: spoken,
                          lambda path, rate: np.zeros(24000 * 4, dtype=np.float32))


def words_heard(texts, shift=0.0):
    return [Heard(t, i * 0.3 + shift, i * 0.3 + shift + 0.2) for i, t in enumerate(texts)]


def test_engine_is_built_from_the_jobs_own_settings_and_pronunciations():
    seen = {}

    def factory(passage):
        seen.update(passage)
        return FakeEngine()

    s3 = FakeS3({EVENT["rawKey"]: raw_v2()})
    deps = make_deps(s3, FakeTable(), factory)
    h.process(EVENT, h.Dependencies(deps.clients, factory, fake_encoder, lambda a: [], lambda p, r: np.zeros(10)))
    assert seen["settings"] == {"voice": "af_bella", "speed": 1.0, "mp3Kbps": 32}
    assert seen["pronunciations"] == {"park": "pahrk"}


def test_review_suspects_are_stored_on_the_timing_and_the_passage_item():
    s3 = FakeS3({EVENT["rawKey"]: raw_v2()})
    table = FakeTable()
    spoken = words_heard(["we", "went", "to", "the", "cart", "it", "was", "fun"])
    h.process(EVENT, v2_deps(s3, table, spoken))
    timing = json.loads(gzip.decompress(s3.objects[f"data/{PASSAGE_ID}.timing.json"]))
    assert timing["review"]["suspects"] == [{"expected": "park", "heard": "cart"}]
    assert table.items[("PASSAGE", PASSAGE_ID)]["review"]["suspects"][0]["expected"] == "park"


def test_a_recording_publishes_a_linked_human_variant_and_both_passage_items():
    key = f"raw/{HUMAN_ID}.audio"
    s3 = FakeS3({EVENT["rawKey"]: raw_v2(recording={"key": key}, humanPassageId=HUMAN_ID), key: b"audio-bytes"})
    table = FakeTable()
    spoken = words_heard(["we", "went", "to", "the", "park", "it", "was", "fun"], shift=0.5)
    result = h.process({**EVENT, "humanPassageId": HUMAN_ID}, v2_deps(s3, table, spoken))
    assert result["status"] == "done"
    human = json.loads(gzip.decompress(s3.objects[f"data/{HUMAN_ID}.timing.json"]))
    ai = json.loads(gzip.decompress(s3.objects[f"data/{PASSAGE_ID}.timing.json"]))
    assert human["engine"] == "human" and human["pairId"] == PASSAGE_ID and ai["pairId"] == HUMAN_ID
    assert human["words"][0]["start_ms"] == 500
    assert s3.content_types[f"data/{HUMAN_ID}.mp3"] == "audio/mpeg"
    assert table.items[("PASSAGE", HUMAN_ID)]["pairId"] == PASSAGE_ID
    assert table.items[("PASSAGE", PASSAGE_ID)]["pairId"] == HUMAN_ID


def test_the_stored_source_label_is_kept_for_regenerated_samples():
    s3 = FakeS3({EVENT["rawKey"]: raw_v2(source="sample", qualityCheck=False)})
    table = FakeTable()
    h.process(EVENT, v2_deps(s3, table, []))
    assert table.items[("PASSAGE", PASSAGE_ID)]["source"] == "sample"


def test_timing_is_stored_gzipped_with_content_encoding_and_audio_is_not():
    s3 = FakeS3({EVENT["rawKey"]: raw_passage()})
    h.process(EVENT, make_deps(s3, FakeTable()))
    assert s3.content_encodings[f"data/{PASSAGE_ID}.timing.json"] == "gzip"
    assert f"data/{PASSAGE_ID}.mp3" not in s3.content_encodings
    assert s3.objects[f"data/{PASSAGE_ID}.timing.json"][:2] == b"\x1f\x8b"


def test_resubmitting_unchanged_input_skips_generation_but_a_changed_setting_regenerates():
    calls = []

    def factory(passage):
        calls.append(1)
        return FakeEngine()

    s3 = FakeS3({EVENT["rawKey"]: raw_v2(qualityCheck=False)})
    table = FakeTable()
    deps = make_deps(s3, table, factory)
    first = h.process(EVENT, deps)
    second = h.process(EVENT, deps)
    assert first["status"] == second["status"] == "done" and len(calls) == 1  # the second run did no synthesis
    assert table.job(JOB_ID)["status"] == "done"
    s3.objects[EVENT["rawKey"]] = raw_v2(qualityCheck=False, settings={"voice": "af_bella", "speed": 1.0, "mp3Kbps": 64})
    h.process(EVENT, deps)
    assert len(calls) == 2  # a changed bitrate regenerates
    s3.objects[EVENT["rawKey"]] = raw_v2(qualityCheck=False, settings={"voice": "af_bella", "speed": 1.0, "mp3Kbps": 64}, force=True)
    h.process(EVENT, deps)
    assert len(calls) == 3  # force always regenerates


def test_a_spanish_job_carries_its_language_to_the_engine_and_the_stored_documents():
    seen = {}

    def factory(passage):
        seen["language"] = passage.get("language")
        return FakeEngine()

    raw = raw_v2(language="es", qualityCheck=False, settings={"voice": "af_heart", "voiceEs": "em_alex", "speed": 1.0, "mp3Kbps": 48})
    s3 = FakeS3({EVENT["rawKey"]: raw})
    table = FakeTable()
    deps = make_deps(s3, table, factory)
    h.process(EVENT, h.Dependencies(deps.clients, factory, fake_encoder, lambda a, **k: [], lambda p, r: np.zeros(10)))
    timing = json.loads(gzip.decompress(s3.objects[f"data/{PASSAGE_ID}.timing.json"]))
    assert seen["language"] == "es" and timing["language"] == "es"
    assert table.items[("PASSAGE", PASSAGE_ID)]["language"] == "es"


def test_the_index_document_is_published_gzipped_and_lists_public_fields_only():
    s3 = FakeS3({EVENT["rawKey"]: raw_v2(qualityCheck=True)})
    table = FakeTable()
    h.process(EVENT, v2_deps(s3, table, words_heard(["we", "went", "to", "the", "park", "it", "was", "fun"])))
    assert s3.content_encodings["data/index.json"] == "gzip"
    index = json.loads(gzip.decompress(s3.objects["data/index.json"]))
    assert [e["id"] for e in index] == [PASSAGE_ID]
    entry = index[0]
    assert set(entry) >= {"id", "title", "words", "durationMs", "engine", "voice", "createdAt", "source", "vocabCount", "language", "pairId"}
    assert not ({"pk", "sk", "metrics", "review"} & set(entry))  # internal fields never leave the table
