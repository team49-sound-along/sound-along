from human_alignment import align_words
from asr_words import Heard


def heard(words, step=0.5, start=0.0):
    return [Heard(w, start + i * step, start + i * step + 0.4) for i, w in enumerate(words)]


def test_exact_match_uses_heard_times_and_flags_aligned():
    out = align_words(["Hello", "world."], heard(["hello", "world"]))
    assert [(w.start_s, w.aligned) for w in out] == [(0.0, True), (0.5, True)]


def test_extra_spoken_words_such_as_a_read_title_are_ignored():
    out = align_words(["Hello", "world."], heard(["my", "title", "hello", "world"]))
    assert out[0].start_s == 1.0 and out[1].start_s == 1.5


def test_number_read_as_a_word_takes_the_heard_time_but_is_not_marked_exact():
    out = align_words(["about", "3", "birds"], heard(["about", "three", "birds"]))
    assert out[1].start_s == 0.5 and out[1].aligned is False


def test_missing_word_is_interpolated_between_neighbours_and_flagged():
    out = align_words(["a", "b", "c", "d"], [Heard("a", 0.0, 0.2), Heard("d", 3.0, 3.2)])
    assert out[0].aligned and out[3].aligned
    assert not out[1].aligned and not out[2].aligned
    assert 0.0 < out[1].start_s < out[2].start_s < 3.0


def test_starts_never_decrease_and_ends_never_precede_starts():
    out = align_words(["x", "y", "z"], [Heard("z", 0.1, 0.3), Heard("x", 5.0, 5.2)])
    starts = [w.start_s for w in out]
    assert starts == sorted(starts)
    assert all(w.end_s >= w.start_s for w in out)


def test_empty_heard_still_returns_one_word_each():
    out = align_words(["a", "b"], [])
    assert len(out) == 2 and not any(w.aligned for w in out)


# --- spelled-out numbers vs the recognizer's digits ("twenty" vs "20") -----------------------------------------------------------
def _h(*words, step=0.5):
    return [Heard(w, i * step, i * step + 0.4) for i, w in enumerate(words)]


def test_a_spoken_number_the_recognizer_wrote_as_digits_matches_the_spelled_word():
    out = align_words(["She", "read", "for", "twenty", "minutes."], _h("She", "read", "for", "20", "minutes"))
    assert [w.aligned for w in out] == [True] * 5
    assert out[3].start_s == 1.5


def test_digits_spoken_as_two_words_are_split_across_the_time_the_recognizer_gave_them():
    out = align_words(["For", "over", "one", "hundred", "years!"], _h("For", "over", "100", "years"))
    assert [w.aligned for w in out] == [True] * 5
    assert out[2].start_s == 1.0 and out[2].end_s <= out[3].start_s <= out[3].end_s  # "one" then "hundred", in order, inside 100's span
    assert out[3].start_s > out[2].start_s


def test_six_million_and_a_hyphenated_compound():
    assert all(w.aligned for w in align_words(["Over", "six", "million", "people"], _h("Over", "6", "million", "people")))
    assert all(w.aligned for w in align_words(["She", "is", "twenty-one", "today"], _h("She", "is", "21", "today")))


def test_digits_the_text_itself_shows_are_left_alone():
    out = align_words(["In", "1767", "the", "£60", "tax", "began."], _h("In", "1767", "the", "£60", "tax", "began"))
    assert [w.aligned for w in out] == [True] * 6


def test_numbers_above_999_are_never_expanded():
    from asr_words import expand_spoken_numbers

    heard = _h("In", "1767", "it", "began")
    assert expand_spoken_numbers(heard, ["In", "seventeen", "sixty-seven", "it", "began"]) == heard  # the text spells it out; still left alone
    assert expand_spoken_numbers(_h("a", "1000", "b"), ["a", "one", "thousand", "b"]) == _h("a", "1000", "b")


def test_expand_spoken_numbers_covers_zero_to_999_and_keeps_order_and_non_numbers():
    from asr_words import expand_spoken_numbers

    out = expand_spoken_numbers(_h("a", "0", "13", "40", "101", "999", "b"), [])
    assert [h.text for h in out] == ["a", "zero", "thirteen", "forty", "one", "hundred", "one", "nine", "hundred", "ninetynine", "b"]
    starts = [h.start_s for h in out]
    assert starts == sorted(starts) and all(h.end_s >= h.start_s for h in out)


def test_a_word_that_merely_contains_digits_is_not_expanded():
    from asr_words import expand_spoken_numbers

    heard = _h("3rd", "1700s", "A4")
    assert expand_spoken_numbers(heard, []) == heard


def test_estimated_words_squeezed_into_a_short_stretch_never_overlap_the_next_word():
    display = ["Start"] + ["razón"] * 12 + ["End"]
    heard = [Heard("start", 0.0, 0.4), Heard("end", 1.2, 1.5)]  # twelve words, 0.8 s of audio between the anchors
    words = align_words(display, heard)
    assert [w.aligned for w in words].count(False) == 12
    for a, b in zip(words, words[1:]):
        assert a.end_s <= b.start_s + 1e-9 and a.start_s <= a.end_s
    starts = [w.start_s for w in words]
    assert starts == sorted(starts)


def test_a_normal_aligned_word_keeps_its_own_end_time():
    words = align_words(["Hello", "world"], [Heard("hello", 0.0, 0.5), Heard("world", 0.6, 1.1)])
    assert (words[0].start_s, words[0].end_s, words[1].end_s) == (0.0, 0.5, 1.1)


def test_words_the_recognizer_missed_at_the_end_never_run_past_the_audio():
    display = ["a", "b", "c", "d", "e", "f"]
    out = align_words(display, [Heard("a", 0.0, 0.3), Heard("b", 0.4, 0.7)], duration_s=2.0)
    assert all(w.end_s <= 2.0 for w in out) and all(w.start_s < 2.0 for w in out)
    assert [w.start_s for w in out] == sorted(w.start_s for w in out)
    assert [w.aligned for w in out] == [True, True, False, False, False, False]


def test_without_a_duration_nothing_changes():
    out = align_words(["a", "b", "c"], [Heard("a", 0.0, 0.3)])
    assert out[2].start_s == out[0].end_s + 2 * 0.3
