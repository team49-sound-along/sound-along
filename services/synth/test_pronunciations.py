import json

from pronunciations import apply_overrides, build_phonemes, load_respellings, soften_stress


def test_apply_overrides_wraps_whole_words_only_and_keeps_case_and_punctuation():
    out = apply_overrides("Gaieties, and gaiety.", {"gaieties": "ɡˈAətiz"})
    assert out == "[Gaieties](/ɡˈAətiz/), and gaiety."


def test_longest_word_wins_and_no_overrides_is_a_noop():
    assert apply_overrides("plain text", {}) == "plain text"
    out = apply_overrides("unseldom", {"un": "X", "unseldom": "Y"})
    assert out == "[unseldom](/Y/)"


def test_build_phonemes_skips_unconvertible_respellings():
    result = build_phonemes({"a": "x", "b": "y"}, lambda s: "AA" if s == "x" else "  ")
    assert result == {"a": "AA"}


def test_load_respellings_ignores_comment_keys_and_missing_file(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"_note": "ignore me", "Gaieties": "gay uh teez"}))
    assert load_respellings(f) == {"gaieties": "gay uh teez"}
    assert load_respellings(tmp_path / "missing.json") == {}


def test_soften_stress_keeps_first_primary_only():
    assert soften_stress("\u0261\u02c8A\u02c8\u028ct\u02c8iz") == "\u0261\u02c8A\u02cc\u028ct\u02cciz"
    assert soften_stress("no stress") == "no stress"


def test_direct_phonemes_are_used_verbatim_and_spaces_removed_from_respellings():
    result = build_phonemes({"a": "/xYz/", "b": "foo"}, lambda s: "a \u02c8b \u02c8c")
    assert result == {"a": "xYz", "b": "a\u02c8b\u02ccc"}
