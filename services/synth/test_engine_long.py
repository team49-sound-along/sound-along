"""Kokoro cuts a Spanish sentence off after about 510 phonemes (roughly 60 words) without any error, so long Spanish sentences are narrated in pieces."""
import types

import numpy as np

import engine as eng


def test_a_short_sentence_is_one_piece():
    assert eng.split_for_tts("Hola, ¿cómo estás?", 40) == ["Hola, ¿cómo estás?"]


def test_a_long_sentence_is_cut_at_commas_and_semicolons_into_pieces_of_at_most_the_limit():
    text = ", ".join(" ".join(f"palabra{i}x{j}" for j in range(12)) for i in range(10)) + "."
    pieces = eng.split_for_tts(text, 40)
    assert len(pieces) > 1 and all(len(p.split()) <= 40 for p in pieces)
    assert " ".join(pieces).replace(" ,", ",") .split() == text.split()  # nothing lost, nothing reordered


def test_a_stretch_with_no_punctuation_is_cut_by_words():
    text = " ".join(f"w{i}" for i in range(130))
    pieces = eng.split_for_tts(text, 40)
    assert [len(p.split()) for p in pieces] == [40, 40, 40, 10] and " ".join(pieces) == text


def make_engine(language, calls):
    e = eng.KokoroEngine.__new__(eng.KokoroEngine)
    e.language, e.native_timing, e.voice, e._speed, e._phonemes = language, language == "en", "v", 1.0, {}

    def pipeline(text, voice, speed):
        calls.append(text)
        yield types.SimpleNamespace(audio=np.ones(2400, dtype=np.float32), tokens=[])
    e._pipeline = pipeline
    return e


def test_spanish_narration_sends_every_piece_to_the_engine_and_keeps_all_the_audio():
    calls: list[str] = []
    text = ", ".join(" ".join(f"p{i}x{j}" for j in range(12)) for i in range(10)) + "."
    out = make_engine("es", calls).synthesize(text)
    assert len(calls) > 1 and all(len(c.split()) <= 40 for c in calls)
    assert len(out.audio) >= 2400 * len(calls)


def test_english_is_sent_as_it_was_because_kokoro_splits_english_itself():
    calls: list[str] = []
    text = " ".join(f"w{i}" for i in range(130))
    make_engine("en", calls).synthesize(text)
    assert calls == [text]
