from asr_words import Heard
from review import find_suspects


def hear(words):
    return [Heard(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate(words)]


def test_a_clearly_different_word_is_a_suspect():
    out = find_suspects(["they", "enjoy", "gaieties", "here"], hear(["they", "enjoy", "deities", "here"]))
    assert out == [{"expected": "gaieties", "heard": "deities"}]


def test_spelling_variants_are_not_suspects():
    words = ["honours", "behaviour", "enquiries", "protestors", "parlour,"]
    assert find_suspects(words, hear(["honors", "behavior", "inquiries", "protesters", "parlor"])) == []


def test_numbers_written_either_way_are_ignored():
    assert find_suspects(["about", "3", "birds"], hear(["about", "three", "birds"])) == []


def test_punctuation_is_stripped_from_the_reported_word_and_duplicates_are_merged():
    out = find_suspects(["a", "crate,", "b", "crate."], hear(["a", "creative", "b", "creative"]))
    assert out == [{"expected": "crate", "heard": "creative"}]


def test_very_short_words_and_empty_transcripts_never_flag():
    assert find_suspects(["a", "an", "it"], hear(["the", "on", "at"])) == []
    assert find_suspects(["hello", "world"], []) == []
