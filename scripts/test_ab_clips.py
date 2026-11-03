import numpy as np

import ab_clips


def words(n, step_ms=500):
    return [{"start_ms": i * step_ms, "end_ms": i * step_ms + 400} for i in range(n)]


def test_excerpt_stops_at_about_thirty_seconds_or_the_end_of_a_short_passage():
    first, last = ab_clips.excerpt_range({"words": words(200)})
    assert first == 0 and 55 <= last <= 62  # about 60 words at 2 words/second
    assert ab_clips.excerpt_range({"words": words(10)}) == (0, 10)


def test_spans_use_the_first_start_and_last_end_of_the_chosen_words():
    assert ab_clips.spans_for(words(10), 0, 4) == (0.0, 1.9)


def test_cut_pads_but_stays_inside_the_recording():
    audio = np.ones(24000 * 10, dtype=np.float32)
    clip = ab_clips.cut(audio, 0.0, 2.0)
    assert len(clip) == int((2.0 + ab_clips.PAD_AFTER_S) * 24000)  # no negative start
    assert len(ab_clips.cut(audio, 9.5, 12.0)) == 24000 * 10 - int((9.5 - ab_clips.PAD_BEFORE_S) * 24000)


def test_loudness_matching_brings_quiet_and_loud_clips_to_the_same_level_without_clipping():
    t = np.arange(24000 * 2) / 24000
    quiet = (0.02 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    loud = (0.9 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    a, b = ab_clips.match_loudness(quiet), ab_clips.match_loudness(loud)
    assert abs(ab_clips.speech_rms_db(a) - ab_clips.speech_rms_db(b)) < 1.0
    assert float(np.max(np.abs(a))) <= 1.0 and float(np.max(np.abs(b))) <= 1.0
