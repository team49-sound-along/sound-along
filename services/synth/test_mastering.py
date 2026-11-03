import numpy as np

from mastering import fade_edges, level_match, peak_normalize, rms_db

SR = 24_000


def tone(amplitude: float, seconds: float = 1.0) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_level_match_pulls_sentences_toward_the_median_without_exceeding_the_limit():
    quiet, normal, loud = tone(0.05), tone(0.2), tone(0.8)
    out = level_match([quiet, normal, loud], max_adjust_db=3.0)
    spread_before = rms_db(loud) - rms_db(quiet)
    spread_after = rms_db(out[2]) - rms_db(out[0])
    assert spread_after < spread_before
    assert abs(rms_db(out[0]) - rms_db(quiet)) <= 3.01  # never boosts more than the limit


def test_level_match_does_not_mutate_inputs_and_keeps_length():
    original = tone(0.1)
    snapshot = original.copy()
    out = level_match([original, tone(0.3)])
    assert np.array_equal(original, snapshot)
    assert len(out[0]) == len(original)


def test_fade_edges_starts_and_ends_at_zero():
    faded = fade_edges(tone(0.5), ms=8)
    assert faded[0] == 0.0 and abs(faded[-1]) < 1e-3
    assert np.max(np.abs(faded[SR // 4 : 3 * SR // 4])) > 0.45  # middle untouched


def test_peak_normalize_hits_target_and_never_clips():
    out = peak_normalize(tone(0.2), peak_db=-1.0)
    assert abs(np.max(np.abs(out)) - 10 ** (-1 / 20)) < 1e-3


def test_silence_is_safe_everywhere():
    silent = np.zeros(SR, dtype=np.float32)
    assert np.all(level_match([silent, silent])[0] == 0)
    assert np.all(peak_normalize(silent) == 0)
    assert np.all(fade_edges(silent) == 0)
    assert len(fade_edges(np.zeros(0, dtype=np.float32))) == 0
