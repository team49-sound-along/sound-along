"""Live place cards on the AWS publish path: written next to the audio, never able to fail a job, never replacing reviewed cards."""
import json

import handler as h
from clients import Clients
from enrich_places import Enriched
from fakes import EVENT, PASSAGE_ID, FakeEngine, FakeS3, FakeTable, fake_encoder

BUCKET = "test-bucket"
JPEG = b"\xff\xd8\xff\xe0" + b"j" * 50
NAME = f"{PASSAGE_ID}.place-piedmont-park-0a1b2c3d.jpg"
ENRICHED = Enriched(
    {"words": {}, "places": {"Piedmont Park": {"name": "Piedmont Park", "summary": "Urban park.", "attribution": "Wikipedia, CC BY-SA",
                                               "imageUrl": f"/data/{NAME}", "imageAlt": "A lake.", "imageCredit": "Photo: A, CC BY 4.0, via Wikimedia Commons"}},
     "reviewed": False, "source": "wikipedia"},
    {NAME: JPEG},
)


def make(enrich_fn=None, objects=None):
    from fakes import raw_passage

    s3 = FakeS3({EVENT["rawKey"]: raw_passage(), **(objects or {})})
    deps = h.Dependencies(Clients(s3=s3, table=FakeTable(), bucket=BUCKET), FakeEngine, fake_encoder, **({"enrich_fn": enrich_fn} if enrich_fn else {}))
    return s3, deps


def test_cards_and_pictures_are_published_next_to_the_audio_with_the_right_types_and_a_long_cache_for_pictures():
    seen = []
    s3, deps = make(lambda passage: seen.append(passage) or ENRICHED)
    h.process(EVENT, deps)
    assert json.loads(s3.objects[f"data/{PASSAGE_ID}.cards.json"])["places"]["Piedmont Park"]["imageUrl"] == f"/data/{NAME}"
    assert s3.content_types[f"data/{PASSAGE_ID}.cards.json"] == "application/json"
    assert s3.objects[f"data/{NAME}"] == JPEG and s3.content_types[f"data/{NAME}"] == "image/jpeg"
    assert s3.cache_controls[f"data/{NAME}"] == "public, max-age=31536000, immutable"
    assert seen[0]["uuid"] == PASSAGE_ID and seen[0]["source"] == "generated"  # the raw input marks it teacher-generated


def test_a_failing_enrichment_never_fails_the_job_and_the_audio_still_publishes():
    def boom(passage):
        raise RuntimeError("wikipedia exploded")

    s3, deps = make(boom)
    h.process(EVENT, deps)
    assert f"data/{PASSAGE_ID}.mp3" in s3.objects and f"data/{PASSAGE_ID}.timing.json" in s3.objects
    assert f"data/{PASSAGE_ID}.cards.json" not in s3.objects


def test_no_places_means_no_cards_file():
    s3, deps = make(lambda passage: None)
    h.process(EVENT, deps)
    assert f"data/{PASSAGE_ID}.cards.json" not in s3.objects


def test_cards_a_person_already_reviewed_are_never_replaced():
    reviewed = json.dumps({"words": {}, "places": {}, "reviewed": True}).encode()
    s3, deps = make(lambda passage: ENRICHED, {f"data/{PASSAGE_ID}.cards.json": reviewed})
    h.process(EVENT, deps)
    assert s3.objects[f"data/{PASSAGE_ID}.cards.json"] == reviewed and f"data/{NAME}" not in s3.objects


def test_by_default_nothing_is_enriched_so_unit_tests_never_touch_the_network():
    s3, deps = make()
    h.process(EVENT, deps)
    assert f"data/{PASSAGE_ID}.cards.json" not in s3.objects


def test_the_production_handler_turns_enrichment_on(monkeypatch):
    captured = {}
    monkeypatch.setattr(h, "create_clients", lambda: Clients(s3=FakeS3(), table=FakeTable(), bucket=BUCKET))
    monkeypatch.setattr(h, "process", lambda event, deps: captured.setdefault("deps", deps) and {"status": "ok"})
    h.handler({}, None)
    assert captured["deps"].enrich_fn is h.live_enrichment
