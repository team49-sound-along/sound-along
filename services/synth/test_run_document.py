"""A long upload becomes one passage per language: chunks are narrated in a work folder, joined, and published together."""
import json

import numpy as np

import run_local as rl
from engine import SAMPLE_RATE as SR
from translate_flow import translated_id


def write_chunk(folder, pid, texts, lang, seconds=2.0, extra=None, cards=None):
    words = [{"i": i, "text": t, "start_ms": i * 500, "end_ms": i * 500 + 400, "sentence": i // 2, "paragraph": 0, "aligned": True, "phraseEnd": False} for i, t in enumerate(texts)]
    timing = {"id": pid, "title": "Doc", "engine": "kokoro", "voice": "af_heart" if lang == "en" else "ef_dora", "duration_ms": round(seconds * 1000),
              "metrics": {"characters": 10, "words": len(words), "audioSeconds": seconds, "generateSeconds": 1.0, "realTimeFactor": 0.5, "unalignedWords": 0},
              "vocab": {}, "words": words, "language": lang, "generatedWith": {"settings": {}, "hash": "h"}, "held": True, **(extra or {})}
    (folder / f"{pid}.timing.json").write_text(json.dumps(timing))
    np.save(folder / f"{pid}.pcm.npy", (np.sin(np.linspace(0, 300, int(SR * seconds))) * 9000).astype(np.int16))
    if cards:
        (folder / f"{pid}.cards.json").write_text(json.dumps(cards))
    return timing


PASSAGE = {"uuid": "11111111-1111-4111-8111-111111111111", "title": "The Long Story", "content": "<p>full text</p>", "language": "en", "source": "generated",
           "settings": {"mp3Kbps": 48}, "pronunciations": {}, "chunks": ["<p>one two three four</p>", "<p>five six seven eight</p>", "<p>nine ten eleven twelve</p>"]}


def fake_run(job, work, on_step=None):
    k = int(job["content"] == PASSAGE["chunks"][1]) + 2 * int(job["content"] == PASSAGE["chunks"][2])
    texts = [["a", "b", "c", "d"], ["e", "f", "g", "h"], ["i", "j", "k", "l"]][k]
    cards = {"words": {f"w{k}": {"word": f"w{k}", "imageUrl": f"/data/{job['uuid']}.word-w{k}-1.png"}}, "places": {}, "reviewed": False}
    write_chunk(work, job["uuid"], texts, "en", extra={"translations": {}}, cards=cards)
    (work / f"{job['uuid']}.word-w{k}-1.png").write_bytes(b"PNG" + bytes([k]))
    return {"id": job["uuid"], "humanPassageId": None}


def fake_translate(job, work, summary):
    tid = translated_id(summary["id"], "es")
    write_chunk(work, tid, ["w", "x", "y", "z"], "es", extra={"machineTranslated": True, "translationOf": {"id": summary["id"], "lang": "en", "sentenceMap": [0, 1]}})
    en = json.loads((work / f"{summary['id']}.timing.json").read_text())
    en["translations"] = {"es": {"id": tid, "sentenceMap": [[0], [1]]}}
    (work / f"{summary['id']}.timing.json").write_text(json.dumps(en))
    return tid


def run(tmp_path, **kw):
    seen = []
    out = rl.run_document(PASSAGE, tmp_path, on_chunk=lambda d, t: seen.append((d, t)), on_step=lambda s: None, run_fn=fake_run, translate_fn=fake_translate, **kw)
    return out, seen


def test_three_chunks_become_one_english_and_one_spanish_passage_listed_together_with_no_trace_of_chunks(tmp_path):
    out, progress = run(tmp_path)
    es_id = translated_id(PASSAGE["uuid"], "es")
    assert progress == [(1, 3), (2, 3), (3, 3)] and out["id"] == PASSAGE["uuid"] and out["words"] == 12
    en = json.loads((tmp_path / f"{PASSAGE['uuid']}.timing.json").read_text())
    es = json.loads((tmp_path / f"{es_id}.timing.json").read_text())
    assert en["title"] == "The Long Story" and "series" not in en and "held" not in en and "held" not in es
    assert [w["text"] for w in en["words"]] == list("abcdefghijkl") and [w["i"] for w in es["words"]] == list(range(12))
    assert en["translations"]["es"]["id"] == es_id and es["translationOf"]["id"] == PASSAGE["uuid"] and es["machineTranslated"] is True
    assert en["translations"]["es"]["sentenceMap"] == [[0], [1], [2], [3], [4], [5]] and es["translationOf"]["sentenceMap"] == [0, 1, 2, 3, 4, 5]
    assert (tmp_path / f"{PASSAGE['uuid']}.mp3").stat().st_size > 1000 and (tmp_path / f"{es_id}.mp3").stat().st_size > 1000
    assert (tmp_path / f"{PASSAGE['uuid']}.soundalong.json").exists() and (tmp_path / f"{es_id}.soundalong.json").exists()
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.endswith(".timing.json")) == sorted([f"{PASSAGE['uuid']}.timing.json", f"{es_id}.timing.json"])


def test_the_work_folder_is_gone_afterwards_even_when_a_chunk_fails(tmp_path):
    run(tmp_path)
    assert not (tmp_path / "work" / PASSAGE["uuid"]).exists()

    def boom(job, work, on_step=None):
        raise RuntimeError("chunk failed")

    try:
        rl.run_document(PASSAGE, tmp_path, on_chunk=lambda d, t: None, on_step=lambda s: None, run_fn=boom, translate_fn=fake_translate)
        raise AssertionError("expected an error")
    except RuntimeError:
        pass
    assert not (tmp_path / "work" / PASSAGE["uuid"]).exists()


def test_cards_from_every_chunk_are_joined_and_their_pictures_belong_to_the_final_passage(tmp_path):
    run(tmp_path)
    pid = PASSAGE["uuid"]
    cards = json.loads((tmp_path / f"{pid}.cards.json").read_text())
    assert set(cards["words"]) == {"w0", "w1", "w2"} and all(c["imageUrl"].startswith(f"/data/{pid}.") for c in cards["words"].values())
    assert sorted(p.name for p in tmp_path.iterdir() if ".word-" in p.name and p.name.startswith(pid)) == [f"{pid}.word-w{k}-1.png" for k in range(3)]


def test_when_one_chunks_translation_is_missing_the_passage_is_published_in_its_own_language_only(tmp_path):
    def flaky(job, work, summary):
        if job["content"] != PASSAGE["chunks"][1]:
            return fake_translate(job, work, summary)
        return None  # this chunk's translation failed

    rl.run_document(PASSAGE, tmp_path, on_chunk=lambda d, t: None, on_step=lambda s: None, run_fn=fake_run, translate_fn=flaky)
    en = json.loads((tmp_path / f"{PASSAGE['uuid']}.timing.json").read_text())
    assert "translations" not in en and "held" not in en
    assert not (tmp_path / f"{translated_id(PASSAGE['uuid'], 'es')}.timing.json").exists()


def test_a_passage_that_will_not_be_translated_is_published_alone(tmp_path):
    passage = {**PASSAGE, "settings": {"translate": False, "mp3Kbps": 48}}
    rl.run_document(passage, tmp_path, on_chunk=lambda d, t: None, on_step=lambda s: None, run_fn=fake_run, translate_fn=lambda *a: (_ for _ in ()).throw(AssertionError("must not translate")))
    assert (tmp_path / f"{PASSAGE['uuid']}.timing.json").exists() and not (tmp_path / f"{translated_id(PASSAGE['uuid'], 'es')}.timing.json").exists()


def test_chunk_ids_are_stable_distinct_and_never_the_documents_own_id():
    ids = [rl.chunk_id(PASSAGE["uuid"], k) for k in range(5)]
    assert ids == [rl.chunk_id(PASSAGE["uuid"], k) for k in range(5)] and len(set(ids)) == 5 and PASSAGE["uuid"] not in ids
