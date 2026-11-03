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
