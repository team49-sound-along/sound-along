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
