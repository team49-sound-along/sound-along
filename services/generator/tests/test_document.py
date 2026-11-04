"""A long document on AWS: every chunk runs through the ordinary generator in a private work folder, then one invocation joins them into ONE passage."""
import gzip
import json

import handler as h
from clients import Clients
from fakes import FakeEngine, FakeS3, FakeTable, fake_encoder, raw_passage
from workspace import NullTable, PrefixedS3, work_prefix

BUCKET = "test-bucket"
FINAL = "33333333-3333-4333-8333-333333333333"
JOB = "44444444-4444-4444-8444-444444444444"
CHUNKS = ["55555555-5555-4555-8555-55555555550%d" % k for k in range(2)]
TEXTS = ["<p>We went to the park. It was fun.</p>", "<p>Then we went home. We were happy.</p>"]


def fake_model(texts):
    return ["ES " + t for t in texts]


def chunk_deps(s3):
    clients = Clients(s3=PrefixedS3(s3, FINAL), table=NullTable(), bucket=BUCKET)
    return h.Dependencies(clients, FakeEngine, fake_encoder, localize_fn=lambda names, s, t: {}, translate_model=lambda s, t, w=None: fake_model, keep_pcm=True)


def real_deps(s3, table):
    return h.Dependencies(Clients(s3=s3, table=table, bucket=BUCKET), FakeEngine, fake_encoder)


def setup(translate=True):
    raw = {"uuid": FINAL, "title": "The Long Story", "content": "".join(TEXTS), "source": "generated", "settings": {} if translate else {"translate": False}}
    objects = {f"raw/{FINAL}.json": json.dumps(raw).encode()}
    for cid, text in zip(CHUNKS, TEXTS):
        objects[f"raw/{cid}.json"] = json.dumps({"uuid": cid, "title": "The Long Story", "content": text, "source": "generated", **({} if translate else {"settings": {"translate": False}})}).encode()
    return FakeS3(objects), FakeTable()


def run_chunks(s3, translate=True):
    for cid in CHUNKS:
        event = {"jobId": JOB, "passageId": cid, "rawKey": f"raw/{cid}.json", "title": "The Long Story", "workFor": FINAL}
        assert h.process(event, chunk_deps(s3))["status"] == "done"
        if translate:
            assert h.process_translation({**event, "mode": "translate"}, chunk_deps(s3))["status"] == "done"


def stitch_event():
    return {"mode": "stitch", "jobId": JOB, "passageId": FINAL, "rawKey": f"raw/{FINAL}.json", "chunkIds": CHUNKS, "title": "The Long Story"}


def timing(s3, pid):
    return json.loads(gzip.decompress(s3.objects[f"data/{pid}.timing.json"]))


def test_a_chunk_never_leaves_the_work_folder_and_is_never_listed():
    s3, table = setup()
    run_chunks(s3)
    assert not [k for k in s3.objects if k.startswith("data/")], "nothing public exists before the join"
    assert any(k == f"{work_prefix(FINAL)}{CHUNKS[0]}.pcm.npy" for k in s3.objects) and any(k.endswith(".mp3") for k in s3.objects if k.startswith(work_prefix(FINAL)))
    assert not [k for k in table.items if k[0] == "PASSAGE"] and not table.items.get(("JOB", JOB)), "no summary, and the person's job is untouched"


def test_the_join_publishes_one_english_and_one_spanish_passage_together_and_cleans_up():
    s3, table = setup()
    run_chunks(s3)
    out = h.process_stitch(stitch_event(), real_deps(s3, table))
    es_id = h.translated_id(FINAL, "es")
    assert out == {"status": "done", "jobId": JOB, "passageId": FINAL, "language": "en"}
    en, es = timing(s3, FINAL), timing(s3, es_id)
    assert en["title"] == "The Long Story" and "series" not in en and "held" not in en and "held" not in es
    assert [w["text"] for w in en["words"]][:3] == ["We", "went", "to"] and [w["i"] for w in en["words"]] == list(range(len(en["words"])))
    assert en["translations"]["es"]["id"] == es_id and es["translationOf"]["id"] == FINAL
    assert len(en["translations"]["es"]["sentenceMap"]) == len({w["sentence"] for w in en["words"]}) and len(es["translationOf"]["sentenceMap"]) == len({w["sentence"] for w in es["words"]})
    assert s3.objects[f"data/{FINAL}.mp3"].startswith(b"MP3:") and f"data/{es_id}.mp3" in s3.objects and f"data/{FINAL}.soundalong.json" in s3.objects
    listed = [e["id"] for e in json.loads(gzip.decompress(s3.objects["data/index.json"]))]
    assert set(listed) == {FINAL, es_id}, "both languages are in the index, and nothing else (no chunk)"
    assert {k[1] for k in table.items if k[0] == "PASSAGE"} == {FINAL, es_id} and "held" not in table.items[("PASSAGE", FINAL)]
    job = table.job(JOB)
    assert job["status"] == "done" and job["passageId"] == FINAL and job["metrics"]["words"] == len(en["words"])
    assert not [k for k in s3.objects if k.startswith(work_prefix(FINAL))], "the work folder is gone (the listing was followed across pages)"


def test_the_audio_timeline_is_one_continuous_passage():
    s3, table = setup()
    run_chunks(s3)
    h.process_stitch(stitch_event(), real_deps(s3, table))
    w = timing(s3, FINAL)["words"]
    assert all(w[i]["start_ms"] <= w[i + 1]["start_ms"] for i in range(len(w) - 1))
    first_of_second = next(x for x in w if x["text"] == "Then")
    assert first_of_second["start_ms"] > w[first_of_second["i"] - 1]["end_ms"] + 400  # the pause between the two chunks


def test_a_chunk_that_did_not_finish_publishes_nothing_and_fails_the_job_with_the_friendly_message():
    s3, table = setup()
    run_chunks(s3)
    del s3.objects[f"{work_prefix(FINAL)}{CHUNKS[1]}.pcm.npy"]
    out = h.process_stitch(stitch_event(), real_deps(s3, table))
    assert out["status"] == "failed"
    assert not [k for k in s3.objects if k.startswith("data/") and k != "data/index.json"] and not [k for k in table.items if k[0] == "PASSAGE"]
    assert table.job(JOB)["status"] == "failed" and "audio" in table.job(JOB)["error"]


def test_when_a_chunks_translation_is_missing_the_document_is_published_in_its_own_language_only():
    s3, table = setup()
    run_chunks(s3)
    for key in [k for k in s3.objects if k.startswith(work_prefix(FINAL)) and h.translated_id(CHUNKS[1], "es") in k]:
        del s3.objects[key]
    out = h.process_stitch(stitch_event(), real_deps(s3, table))
    assert out["status"] == "done" and "translations" not in timing(s3, FINAL)
    assert [e["id"] for e in json.loads(gzip.decompress(s3.objects["data/index.json"]))] == [FINAL]


def test_a_document_that_is_not_translated_is_published_alone():
    s3, table = setup(translate=False)
    run_chunks(s3, translate=False)
    assert h.process_stitch(stitch_event(), real_deps(s3, table))["status"] == "done"
    assert [k for k in s3.objects if k.endswith(".timing.json") and k.startswith("data/")] == [f"data/{FINAL}.timing.json"]


def test_the_work_stand_ins_behave():
    s3 = FakeS3({})
    prefixed = PrefixedS3(s3, FINAL)
    prefixed.put_object(Bucket=BUCKET, Key="data/a.timing.json", Body=b"x", ContentType="application/json")
    prefixed.put_object(Bucket=BUCKET, Key="raw/keep.json", Body=b"y", ContentType="application/json")
    assert set(s3.objects) == {f"{work_prefix(FINAL)}a.timing.json", "raw/keep.json"} and prefixed.get_object(Bucket=BUCKET, Key="data/a.timing.json")["Body"].read() == b"x"
    t = NullTable()
    t.put_item(Item={"pk": "PASSAGE"}); t.update_item(Key={})
    assert t.query(KeyConditionExpression="pk = :pk", ExpressionAttributeValues={":pk": "PASSAGE"}) == {"Items": []}
