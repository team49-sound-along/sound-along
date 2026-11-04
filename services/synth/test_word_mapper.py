from word_mapper import EngineToken, map_words


def tok(text, a, b):
    return EngineToken(text, a, b)


def test_punctuation_and_contraction_tokens_are_merged():
    engine = [tok("there", 0.0, 0.2), tok("'s", 0.2, 0.3), tok("a", 0.3, 0.4), tok("park", 0.4, 0.8), tok(".", 0.8, 0.9)]
    words = map_words(["there's", "a", "park."], engine)
    assert [w.aligned for w in words] == [True, True, True]
    assert (words[0].start_s, words[0].end_s) == (0.0, 0.3)
    assert (words[2].start_s, words[2].end_s) == (0.4, 0.9)


def test_mismatch_is_marked_not_raised():
    engine = [tok("completely", 0.0, 0.5), tok("different", 0.5, 1.0)]
    words = map_words(["hello", "world"], engine)
    assert len(words) == 2
    assert not all(w.aligned for w in words)


def test_punctuation_only_display_token_uses_previous_end():
    engine = [tok("wait", 0.0, 0.4), tok("go", 0.5, 0.8)]
    words = map_words(["wait", "—", "go"], engine)
    assert words[1].start_s == words[1].end_s == 0.4
    assert words[2].aligned


def test_missing_timestamps_fall_back_and_flag():
    words = map_words(["hi"], [tok("hi", None, None)], fallback_start=2.0)
    assert words[0].start_s == 2.0 and not words[0].aligned


def test_ends_never_precede_starts():
    words = map_words(["a"], [tok("a", 1.0, 0.5)])
    assert words[0].end_s >= words[0].start_s


def test_a_word_never_ends_after_the_next_one_starts():
    engine = [tok("cien", 1.0, 1.4), tok("años", 1.2, 1.8), tok("!", 1.8, 1.9)]  # the recognizer let two words overlap by 0.2 s
    words = map_words(["cien", "años!"], engine)
    assert words[0].end_s <= words[1].start_s
    assert words[0].start_s <= words[0].end_s and words[1].start_s <= words[1].end_s
