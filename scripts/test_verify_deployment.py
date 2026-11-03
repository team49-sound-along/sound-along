import hashlib

import verify_deployment as v


def test_sha256_matches_the_known_digest_the_cloudfront_oac_requires():
    assert v.sha256_hex(b"abc") == hashlib.sha256(b"abc").hexdigest()
    assert v.sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_content_range_parsing():
    assert v.parse_content_range("bytes 0-1023/52000") == (0, 1023, 52000)
    assert v.parse_content_range("items 0-1/2") is None
    assert v.parse_content_range("garbage") is None
    assert v.parse_content_range("") is None


def test_monotonic_start_check_catches_a_word_that_jumps_backwards():
    assert v.monotonic_starts([{"start_ms": 0}, {"start_ms": 10}, {"start_ms": 10}])
    assert not v.monotonic_starts([{"start_ms": 0}, {"start_ms": 500}, {"start_ms": 400}])
    assert v.monotonic_starts([])


def test_report_counts_failures_and_a_crashing_check_becomes_a_fail_not_a_crash(capsys):
    report = v.Report()
    report.check("ok", lambda: "fine")
    report.check("assertion", lambda: (_ for _ in ()).throw(AssertionError("bad")))
    report.check("crash", lambda: 1 / 0)
    out = capsys.readouterr().out
    assert report.failed == 2 and "PASS  ok" in out and "FAIL  assertion: bad" in out and "ZeroDivisionError" in out


def test_cards_are_required_only_for_english_sample_texts_with_the_read_aloud_voice():
    sample = {"id": "a", "source": "sample", "language": "en", "engine": "kokoro"}
    assert v.needs_cards(sample)
    assert not v.needs_cards({**sample, "engine": "human"})  # the human variant opens the AI passage's cards
    assert not v.needs_cards({**sample, "language": "es"})
    assert not v.needs_cards({**sample, "source": "generated"})  # teacher uploads and the verifier's own job have none
    assert not v.needs_cards({})


def test_cards_document_validation():
    good = {"words": {"relax": {"word": "relax"}}, "places": {}}
    assert v.cards_problem(good) is None
    assert "words" in v.cards_problem({"places": {}})
    assert "no word cards" in v.cards_problem({"words": {}, "places": {}})
    assert v.cards_problem([]) is not None


def test_image_urls_are_collected_from_place_cards_only_and_must_stay_on_our_own_origin():
    doc = {"words": {"relax": {"word": "relax", "imageUrl": "/data/x.word-relax-12345678.png"}}, "places": {
        "A": {"imageUrl": "/data/x.place-a-12345678.jpg"}, "B": {"imageUrl": None}, "C": {}}}
    assert v.image_urls(doc) == ["/data/x.place-a-12345678.jpg", "/data/x.word-relax-12345678.png"]
    assert v.cards_problem({"words": {"w": {}}, "places": {"A": {"imageUrl": "https://example.com/a.jpg"}}}) is not None
    assert v.cards_problem({"words": {"w": {}}, "places": {"A": {"imageUrl": "/data/x.place-a-12345678.jpg"}}}) is None
