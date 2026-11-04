"""Translation on AWS: a second invocation of the generator that works in S3 and DynamoDB, links every variant, and never fails a job."""
import gzip
import json

import handler as h
from clients import Clients
from fakes import EVENT, PASSAGE_ID, FakeEngine, FakeS3, FakeTable, fake_encoder, raw_passage

BUCKET = "test-bucket"
HUMAN = "181b9f7b-6e16-57ce-bec2-a48c90d591d0"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (72).to_bytes(4, "big") * 2 + b"\x08\x06\x00\x00\x00" + b"p" * 30


def fake_model(texts):
    return ["ES " + t for t in texts]


def deps_for(s3, table, with_model=True):
    kwargs = {"translate_model": (lambda s, t, w=None: fake_model)} if with_model else {}
    return h.Dependencies(Clients(s3=s3, table=table, bucket=BUCKET), FakeEngine, fake_encoder, localize_fn=lambda names, s, t: {}, **kwargs)


def published(content="<p>We went to the park. It was fun.</p>", settings=None, source="generated", with_human=False, cards=False):
    raw = json.loads(raw_passage(content=content))
    raw.update({"source": source, **({"settings": settings} if settings else {})})
    s3 = FakeS3({EVENT["rawKey"]: json.dumps(raw).encode()})
    table = FakeTable()
    deps = deps_for(s3, table)
    h.process(EVENT, deps)
    if with_human:  # the Library opens the human variant too, so it must be linked as well
        ai = json.loads(gzip.decompress(s3.objects[f"data/{PASSAGE_ID}.timing.json"]))
        s3.objects[f"data/{PASSAGE_ID}.timing.json"] = gzip.compress(json.dumps({**ai, "pairId": HUMAN}).encode())
        s3.objects[f"data/{HUMAN}.timing.json"] = gzip.compress(json.dumps({**ai, "id": HUMAN, "engine": "human", "pairId": PASSAGE_ID}).encode())
        table.items[("PASSAGE", HUMAN)] = {"pk": "PASSAGE", "sk": HUMAN, "id": HUMAN, "title": "T", "createdAt": "2026-01-01T00:00:00Z", "source": "generated", "language": "en"}
    if cards:
        s3.objects[f"data/{PASSAGE_ID}.word-park-0a1b2c3d.png"] = PNG
        s3.objects[f"data/{PASSAGE_ID}.cards.json"] = json.dumps({"words": {"park": {"word": "park", "partOfSpeech": "noun", "definition": "", "spanish": [],
            "imageUrl": f"/data/{PASSAGE_ID}.word-park-0a1b2c3d.png", "imageAlt": "park", "imageCredit": "Picture: OpenMoji, CC BY-SA 4.0"}}, "places": {}}).encode()
    return s3, table, deps


def timing(s3, pid):
    return json.loads(gzip.decompress(s3.objects[f"data/{pid}.timing.json"]))


def run(s3, table, deps):
    return h.process_translation({"mode": "translate", "jobId": EVENT["jobId"], "passageId": PASSAGE_ID, "rawKey": EVENT["rawKey"]}, deps)


def test_process_reports_the_language_so_the_state_machine_can_gate_questions_and_translation():
    s3, table, deps = published()
    out = h.process(EVENT, deps)
    assert out["status"] == "done" and out["language"] == "en"
    es = json.loads(raw_passage(content="<p>Hola mundo.</p>")) | {"language": "es", "source": "generated"}
    s3.objects[EVENT["rawKey"]] = json.dumps(es).encode()
    assert h.process(EVENT, deps)["language"] == "es"


def test_a_translated_passage_is_published_with_its_own_audio_timing_and_summary_and_linked_back():
    s3, table, deps = published()
    out = run(s3, table, deps)
    tid = out["translatedId"]
    assert out["status"] == "done" and tid != PASSAGE_ID
    assert f"data/{tid}.mp3" in s3.objects and s3.content_types[f"data/{tid}.timing.json"] == "application/json"
    t = timing(s3, tid)
    assert t["language"] == "es" and t["machineTranslated"] is True and t["translationOf"]["id"] == PASSAGE_ID and t["translationOf"]["lang"] == "en"
    assert t["words"][0]["text"].startswith("ES")
    item = table.items[("PASSAGE", tid)]
    assert item["language"] == "es" and item["translationOf"] == PASSAGE_ID


def test_the_source_timing_and_summary_gain_the_link_and_keep_their_created_at():
    s3, table, deps = published()
    before = table.items[("PASSAGE", PASSAGE_ID)]["createdAt"]
    tid = run(s3, table, deps)["translatedId"]
    assert timing(s3, PASSAGE_ID)["translations"]["es"]["id"] == tid and timing(s3, PASSAGE_ID)["translations"]["es"]["sentenceMap"]
    item = table.items[("PASSAGE", PASSAGE_ID)]
    assert item["translations"] == {"es": tid} and item["createdAt"] == before


def test_the_human_variant_is_linked_too_and_the_index_carries_every_link():
    s3, table, deps = published(with_human=True)
    tid = run(s3, table, deps)["translatedId"]
    assert timing(s3, HUMAN)["translations"]["es"]["id"] == tid
    index = json.loads(gzip.decompress(s3.objects["data/index.json"]))
    by_id = {e["id"]: e for e in index}
    assert by_id[PASSAGE_ID]["translations"] == {"es": tid} and by_id[HUMAN]["translations"] == {"es": tid} and by_id[tid]["translationOf"] == PASSAGE_ID


def test_translated_cards_and_pictures_are_uploaded_with_an_image_type_and_a_long_cache():
    s3, table, deps = published(content="<p>We went to the park.</p>", cards=True)

    class WordModel:
        def __call__(self, texts):
            return ["parque" if t == "park" else "ES " + t for t in texts]

    deps = h.Dependencies(deps.clients, FakeEngine, fake_encoder, translate_model=lambda s, t, w=None: WordModel(), localize_fn=lambda n, s, t: {})
    tid = run(s3, table, deps)["translatedId"]
    cards = json.loads(s3.objects[f"data/{tid}.cards.json"])
    assert cards["machineTranslated"] is True and cards["words"] == {} or "parque" in cards["words"]
    pics = [k for k in s3.objects if f"data/{tid}.word-" in k]
    for key in pics:
        assert s3.content_types[key] == "image/png" and s3.cache_controls[key] == "public, max-age=31536000, immutable"


def test_nothing_happens_when_translation_is_switched_off_or_not_for_this_passage():
    for kwargs in ({"settings": {"translate": False}}, {"source": "sample"}):
        s3, table, deps = published(**kwargs)
        keys = set(s3.objects)
        out = run(s3, table, deps)
        assert out["status"] == "skipped" and set(s3.objects) == keys
    s3, table, _ = published()
    assert run(s3, table, deps_for(s3, table, with_model=False))["status"] == "skipped"  # no translator configured


def test_a_failing_translation_never_raises_and_leaves_no_dangling_link():
    s3, table, deps = published()

    def boom(source, target):
        raise RuntimeError("model exploded")

    out = run(s3, table, h.Dependencies(deps.clients, FakeEngine, fake_encoder, translate_model=boom))
    assert out["status"] == "failed"
    assert "translations" not in timing(s3, PASSAGE_ID) and not [k for k in table.items if k[0] == "PASSAGE" and k[1] != PASSAGE_ID]


def test_the_lambda_entry_point_routes_translate_events_to_the_translation_mode(monkeypatch):
    seen = {}
    monkeypatch.setattr(h, "create_clients", lambda: Clients(s3=FakeS3(), table=FakeTable(), bucket=BUCKET))
    monkeypatch.setattr(h, "process_translation", lambda event, deps: seen.setdefault("t", (event, deps)) and {"status": "done"})
    monkeypatch.setattr(h, "process", lambda event, deps: {"status": "generation"})
    assert h.handler({"mode": "translate", "passageId": "x"}, None) == {"status": "done"}
    assert seen["t"][1].translate_model is not None and h.handler({"passageId": "x"}, None) == {"status": "generation"}


def test_a_passage_too_long_for_the_lambda_limit_is_skipped_with_a_clear_reason():
    s3, table, deps = published(content="<p>" + "word " * (h.MAX_TRANSLATE_WORDS + 50) + ".</p>")
    out = h.process_translation({"jobId": "j", "passageId": PASSAGE_ID, "rawKey": EVENT["rawKey"]}, deps)
    assert out["status"] == "skipped" and "too long to translate automatically" in out["reason"]


def _spy_deps(deps, names_for=lambda lang: (lambda text: ["Piedmont Park"])):
    calls = []
    return h.Dependencies(deps.clients, FakeEngine, fake_encoder, translate_model=lambda s, t, w=None: fake_model,
                          names_for=names_for, localize_fn=lambda names, s, t: calls.append(list(names)) or {}), calls


def test_names_are_looked_up_on_wikipedia_for_english_sources_only_when_place_lookups_are_allowed():
    s3, table, deps = published(content="<p>We went to Piedmont Park. It was fun.</p>")
    spy, calls = _spy_deps(deps)
    run(s3, table, spy)
    assert calls, "English passages still get localised place names"
    s3, table, deps = published(content="<p>We went to Piedmont Park. It was fun.</p>", settings={"placeCards": False})
    spy, calls = _spy_deps(deps)
    run(s3, table, spy)
    assert calls == [], "a teacher who switched place lookups off must not have names sent to Wikipedia"


def test_the_operator_switch_stops_name_lookups_too(monkeypatch):
    monkeypatch.setenv("PLACE_CARDS", "off")
    s3, table, deps = published(content="<p>We went to Piedmont Park. It was fun.</p>")
    spy, calls = _spy_deps(deps)
    run(s3, table, spy)
    assert calls == []


def test_spanish_sources_never_send_capitalised_names_to_wikipedia():
    s3, table, deps = published(content="<p>Ana y Pablo van al parque. Es divertido.</p>")
    raw = json.loads(s3.objects[EVENT["rawKey"]])
    s3.objects[EVENT["rawKey"]] = json.dumps({**raw, "language": "es"}).encode()
    spy, calls = _spy_deps(deps, names_for=h._names_for)  # the real finder: every capitalised run is a candidate, "Pablo" included
    out = run(s3, table, spy)
    assert out["status"] == "done" and calls == [], "names of people must not leave the system"


def test_translated_cards_that_a_person_reviewed_are_never_overwritten():
    s3, table, deps = published(content="<p>We went to the park.</p>", cards=True)
    tid = run(s3, table, deps)["translatedId"]
    reviewed = json.dumps({"words": {"parque": {"word": "parque", "definition": "Un lugar con árboles."}}, "places": {}, "reviewed": True}).encode()
    s3.objects[f"data/{tid}.cards.json"] = reviewed
    run(s3, table, deps)  # the passage is regenerated and translated again
    assert s3.objects[f"data/{tid}.cards.json"] == reviewed


def test_generated_translated_cards_are_marked_unreviewed_and_machine_translated():
    s3, table, deps = published(content="<p>We went to the park.</p>", cards=True)
    tid = run(s3, table, deps)["translatedId"]
    cards = json.loads(s3.objects[f"data/{tid}.cards.json"])
    assert cards["reviewed"] is False and cards["machineTranslated"] is True and cards["source"] == "translated"


def test_spanish_names_are_not_masked_so_the_model_can_see_who_is_a_girl():
    assert h._names_for("es")("Ana y su hermano Pablo van al parque.") == []
    assert h._names_for("en")("We went to Piedmont Park.") in ([], ["Piedmont Park"])  # spaCy decides; never people


def test_the_translator_is_opus_mt_unless_a_bedrock_model_is_configured(monkeypatch):
    import translate

    sentinel = lambda texts: texts  # noqa: E731
    monkeypatch.setattr(translate, "load_model", lambda source, target, words=None: sentinel)
    monkeypatch.delenv("TRANSLATE_MODEL", raising=False)
    assert h._load_translator("es", "en", 100) is sentinel
    monkeypatch.setenv("TRANSLATE_MODEL", "bedrock:")
    assert h._load_translator("es", "en", 100) is sentinel
