from qa_metrics import Expected, Heard, compare, norm, percentile


def exp(words, step=500):
    return [Expected(i, w, i * step) for i, w in enumerate(words)]


def hear(words, step=0.5, shift=0.0):
    return [Heard(w, i * step + shift, i * step + shift + 0.3) for i, w in enumerate(words)]


def test_perfect_match_has_zero_wer_and_timing_error():
    r = compare(exp(["Hello", "world."]), hear(["hello", "world"]))
    assert r.wer == 0 and r.median_error_ms == 0 and r.within_100ms == 1.0


def test_substitution_is_reported_as_pronunciation_suspect():
    r = compare(exp(["the", "Piedmont", "park"]), hear(["the", "peedmont", "park"]))
    assert r.substitutions == (("Piedmont", "peedmont"),)
    assert abs(r.wer - 1 / 3) < 1e-9


def test_deletion_and_insertion_counted():
    r = compare(exp(["a", "b", "c"]), hear(["a", "c", "d"]))
    assert r.deletions == ("b",) and r.insertions == 1


def test_numeric_tokens_are_skipped_not_penalised():
    r = compare(exp(["about", "3", "birds"]), hear(["about", "three", "birds"]))
    assert r.skipped_numeric == 1 and r.words_checked == 2 and r.wer == 0


def test_timing_error_measured_in_ms():
    r = compare(exp(["red", "blue", "green"]), hear(["red", "blue", "green"], shift=0.12))
    assert round(r.median_error_ms) == 120
    assert r.within_100ms == 0.0 and r.within_250ms == 1.0


def test_percentile_edges():
    assert percentile([], 0.5) is None
    assert percentile([5], 0.95) == 5
    assert percentile([0, 10], 0.5) == 5


def test_norm_strips_punctuation_and_case():
    assert norm("There's!") == "theres"
