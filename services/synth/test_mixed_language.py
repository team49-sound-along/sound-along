"""Mixed-language narration: SSML for Polly, mark mapping, retry, switches, Kokoro splice, fingerprint. No AWS, no models."""
import io
import json
import sys
import types
from dataclasses import dataclass

import numpy as np
import pytest

from engine import SAMPLE_RATE, SentenceAudio
from fingerprint import fingerprint
from mixed import ForeignSpan, clean_spans, passage_enabled, segments, spans_for
from mixed_kokoro import CROSSFADE_S, join, splice_sentence
from pipeline import generate
from polly_engine import PollyEngine
from ssml import build_ssml, escape_xml, word_marks
from word_mapper import EngineToken

SENTENCE = "It is called La Calabiuza, in El Salvador."
SPANS = [ForeignSpan(13, 25, "es"), ForeignSpan(30, 41, "es")]  # "La Calabiuza", "El Salvador"


@dataclass(frozen=True)
class Span:  # stand-in with the contract of langspans.Span (tests only)
    start: int
    end: int
    lang: str


def install_detector(monkeypatch, fn):
    module = types.ModuleType("langspans")
    module.detect_spans = fn
    monkeypatch.setitem(sys.modules, "langspans", module)


def stand_in(text, base_lang):
    out = []
    for phrase, lang in (("La Calabiuza", "es"), ("El Salvador", "es")):
        i = text.find(phrase)
        if i >= 0 and base_lang != lang:
            out.append(Span(i, i + len(phrase), lang))
    return out


# ---- SSML builder ---------------------------------------------------------------------------------------------------------------
def test_spans_are_wrapped_in_lang_tags():
    assert SENTENCE[13:25] == "La Calabiuza" and SENTENCE[30:41] == "El Salvador"
    doc = build_ssml(SENTENCE, SPANS)
    assert doc.ssml == ('<speak>It is called <lang xml:lang="es-US">La Calabiuza</lang>, in '
                        '<lang xml:lang="es-US">El Salvador</lang>.</speak>')


def test_english_inside_spanish_uses_en_us():
    assert '<lang xml:lang="en-US">Halloween</lang>' in build_ssml("Es Halloween hoy", [ForeignSpan(3, 12, "en")]).ssml


def test_xml_is_escaped_inside_and_outside_spans():
    text = 'Tom & "Jerry" <b> said El Niño\'s end'
    start = text.index("El")
    doc = build_ssml(text, [ForeignSpan(start, start + 9, "es")])
    assert "Tom &amp; &quot;Jerry&quot; &lt;b&gt; said" in doc.ssml and "El Niño&apos;s" in doc.ssml
    assert "<b>" not in doc.ssml
    assert escape_xml("a\x00b\x0bc") == "a b c"  # characters XML cannot carry


def test_no_spans_is_just_the_escaped_text_in_speak():
    assert build_ssml("a < b", []).ssml == "<speak>a &lt; b</speak>"


def test_overlapping_and_nested_spans_are_cleaned_before_building():
    spans = clean_spans(SENTENCE, [Span(13, 25, "es"), Span(16, 20, "es"), Span(20, 30, "es"), Span(30, 41, "xx"), Span(5, 5, "es"), Span(0, 999, "es")])
    assert spans == [ForeignSpan(13, 25, "es")]
    assert build_ssml(SENTENCE, spans).ssml.count("<lang") == 1


def test_segments_join_back_to_the_text():
    parts = segments(SENTENCE, SPANS, "en")
    assert "".join(t for _, t in parts) == SENTENCE
    assert [lang for lang, _ in parts] == ["en", "es", "en", "es", "en"]


# ---- marks to words, with offsets shifted by the inserted tags -------------------------------------------------------------------
def marks_for(doc, words_times):
    """Recorded-style marks: offsets point into the SSML string (UTF-8 bytes), as Polly returns them."""
    marks, cursor = [], 0
    for word, t in words_times:
        i = doc.ssml.index(word, cursor)
        marks.append({"time": t, "type": "word", "start": len(doc.ssml[:i].encode()), "end": len(doc.ssml[:i + len(word)].encode()), "value": word})
        cursor = i + len(word)
    return marks


WORDS = [("It", 0), ("is", 100), ("called", 200), ("La", 500), ("Calabiuza", 650), ("in", 1100), ("El", 1250), ("Salvador", 1400)]


def test_origin_of_maps_ssml_offsets_back_to_the_sentence_and_markup_to_none():
    doc = build_ssml(SENTENCE, SPANS)
    assert doc.origin_of(doc.ssml.index("Calabiuza")) == SENTENCE.index("Calabiuza")
    assert doc.origin_of(doc.ssml.index("Salvador")) == SENTENCE.index("Salvador")
    assert doc.origin_of(doc.ssml.index("<lang")) is None
    amp = build_ssml("a & b El", [ForeignSpan(6, 8, "es")])
    assert amp.origin_of(amp.ssml.index("b")) == 4  # the entity counts as one character


def test_marks_inside_markup_are_dropped_and_real_words_kept_in_order():
    doc = build_ssml(SENTENCE, SPANS)
    marks = marks_for(doc, WORDS)
    stray = {"time": 480, "type": "word", "start": doc.ssml.index("<lang"), "end": doc.ssml.index("<lang") + 5, "value": "<lang"}
    kept = word_marks(marks[:3] + [stray] + marks[3:] + [{"time": 9, "type": "sentence", "start": 0, "end": 3, "value": "x"}], doc)
    assert [m["value"] for m in kept] == [w for w, _ in WORDS]


def test_non_ascii_byte_offsets_are_understood():
    text = "Mañana vamos a El Salvador"
    doc = build_ssml(text, [ForeignSpan(15, 26, "es")])
    kept = word_marks(marks_for(doc, [("Mañana", 0), ("vamos", 400), ("El", 900), ("Salvador", 1000)]), doc)
    assert len(kept) == 4


class FakePolly:
    def __init__(self, marks_for_text=None, reject_ssml=False, samples=16000):
        self.pcm = (np.ones(samples, dtype="<i2") * 1000).tobytes()
        self.calls, self.reject_ssml, self.marks_for_text = [], reject_ssml, marks_for_text

    def synthesize_speech(self, **kw):
        self.calls.append(kw)
        if kw["TextType"] == "ssml" and self.reject_ssml:
            err = Exception("bad ssml")
            err.response = {"Error": {"Code": "InvalidSsmlException"}}
            raise err
        if kw["OutputFormat"] == "pcm":
            return {"AudioStream": io.BytesIO(self.pcm)}
        marks = self.marks_for_text(kw["Text"], kw["TextType"])
        return {"AudioStream": io.BytesIO("\n".join(json.dumps(m) for m in marks).encode())}


def recorded_marks(text, text_type):
    doc = build_ssml(SENTENCE, SPANS) if text_type == "ssml" else None
    if doc is not None:
        assert text == doc.ssml
        return marks_for(doc, WORDS)
    cursor, marks = 0, []
    for word, t in WORDS:
        i = text.index(word, cursor)
        marks.append({"time": t, "type": "word", "start": i, "end": i + len(word), "value": word})
        cursor = i + len(word)
    return marks


def test_polly_sends_ssml_for_both_audio_and_marks_and_maps_every_word():
    client = FakePolly(recorded_marks)
    out = PollyEngine(client).synthesize(SENTENCE, spans=SPANS)
    assert all(c["TextType"] == "ssml" and c["Text"].startswith("<speak>") for c in client.calls) and len(client.calls) == 2
    assert [t.text for t in out.tokens] == [w for w, _ in WORDS] and out.spans_applied == 2
    assert out.tokens[3].start_s == 0.5 and out.tokens[2].end_s == 0.5  # La starts where "called" ends


def test_invalid_ssml_is_retried_once_without_tags(caplog):
    client = FakePolly(recorded_marks, reject_ssml=True)
    out = PollyEngine(client).synthesize(SENTENCE, spans=SPANS)
    plain = [c for c in client.calls if c["TextType"] == "text"]
    assert [c["Text"] for c in plain] == [SENTENCE, SENTENCE] and out.spans_applied == 0 and len(out.tokens) == len(WORDS)
    assert "retrying without language tags" in caplog.text


def test_other_polly_errors_are_not_swallowed():
    class Boom(FakePolly):
        def synthesize_speech(self, **kw):
            raise RuntimeError("throttled")

    with pytest.raises(RuntimeError):
        PollyEngine(Boom(recorded_marks)).synthesize(SENTENCE, spans=SPANS)


def test_no_spans_is_byte_identical_to_the_old_request():
    client = FakePolly(recorded_marks)
    PollyEngine(client).synthesize(SENTENCE)
    assert {c["TextType"] for c in client.calls} == {"text"} and all(c["Text"] == SENTENCE for c in client.calls)


def test_long_form_voices_never_get_tags_and_generative_needs_no_marks():
    assert PollyEngine(FakePolly(), voice="Alba", engine="long-form").accepts_spans is False
    client = FakePolly(recorded_marks)
    out = PollyEngine(client, engine="generative").synthesize(SENTENCE, spans=SPANS)
    assert [c["OutputFormat"] for c in client.calls] == ["pcm"] and out.spans_applied == 2 and out.tokens == ()


# ---- switches and detection ------------------------------------------------------------------------------------------------------
def test_missing_detector_means_no_spans(monkeypatch):
    monkeypatch.setitem(sys.modules, "langspans", None)  # import raises ImportError
    assert spans_for(SENTENCE, "en") == []


def test_detector_failure_means_no_spans(monkeypatch):
    def boom(text, base):
        raise RuntimeError("model")

    install_detector(monkeypatch, boom)
    assert spans_for(SENTENCE, "en") == []


def test_env_off_and_passage_setting_disable(monkeypatch):
    install_detector(monkeypatch, stand_in)
    assert len(spans_for(SENTENCE, "en")) == 2
    assert passage_enabled({}) and passage_enabled({"settings": {"mixedLanguage": True}})
    assert not passage_enabled({"settings": {"mixedLanguage": False}})
    monkeypatch.setenv("MIXED_LANGUAGE", "off")
    assert not passage_enabled({}) and spans_for(SENTENCE, "en") == []


class RecordingEngine:
    name, voice, accepts_spans = "polly", "Joanna", True

    def __init__(self):
        self.seen = []

    def synthesize(self, sentence, spans=()):
        self.seen.append((sentence, tuple(spans)))
        tokens = tuple(EngineToken(w, i * 0.3, (i + 1) * 0.3) for i, w in enumerate(sentence.split()))
        return SentenceAudio(np.full(SAMPLE_RATE, 0.1, dtype=np.float32), tokens, len(spans))


HTML = "<p>It is called La Calabiuza, in El Salvador.</p>"


def test_pipeline_detects_on_the_synthesized_plain_text_and_counts_spans(monkeypatch):
    install_detector(monkeypatch, stand_in)
    engine = RecordingEngine()
    result = generate(HTML, engine, language="en")
    assert engine.seen[0][0] == SENTENCE and len(engine.seen[0][1]) == 2 and result.foreign_spans == 2


def test_pipeline_without_spans_calls_the_engine_exactly_as_before(monkeypatch):
    install_detector(monkeypatch, stand_in)
    engine = RecordingEngine()
    generate(HTML, engine, language="en", mixed_language=False)
    generate(HTML, engine, language="es")  # stand-in finds no foreign span in a Spanish passage
    assert [spans for _, spans in engine.seen] == [(), ()]


def test_engines_that_cannot_speak_spans_are_never_asked(monkeypatch):
    install_detector(monkeypatch, stand_in)

    class Plain(RecordingEngine):
        accepts_spans = False

        def synthesize(self, sentence):  # no spans parameter at all (Phonon-style)
            return super().synthesize(sentence)

    assert generate(HTML, Plain(), language="en").foreign_spans == 0


# ---- fingerprint ----------------------------------------------------------------------------------------------------------------
def test_fingerprint_follows_the_feature(monkeypatch):
    passage = {"uuid": "p", "content": "<p>Hi</p>", "language": "en", "settings": {}}
    on = fingerprint(passage)
    assert fingerprint({**passage, "settings": {"mixedLanguage": False}}) != on
    monkeypatch.setenv("MIXED_LANGUAGE_KOKORO", "on")
    assert fingerprint(passage) != on
    monkeypatch.delenv("MIXED_LANGUAGE_KOKORO")
    monkeypatch.setenv("MIXED_LANGUAGE", "off")
    assert fingerprint(passage) == fingerprint({**passage, "settings": {"mixedLanguage": False}})  # off == the pre-feature hash
    assert fingerprint(passage) != on


# ---- Kokoro splice (fake engines) -----------------------------------------------------------------------------------------------
def fake_synth(durations, timed=True):
    def synth(lang, text):
        seconds = durations[lang]
        level = 0.1 if lang == "en" else 0.2
        audio = np.full(int(seconds * SAMPLE_RATE), level, dtype=np.float32)
        words = text.split()
        step = seconds / len(words)
        tokens = tuple(EngineToken(w, i * step, (i + 1) * step) for i, w in enumerate(words)) if timed else ()
        return SentenceAudio(audio, tokens)

    return synth


def test_splice_durations_add_up_minus_the_crossfades_and_timeline_is_monotonic():
    out = splice_sentence(SENTENCE, SPANS, "en", fake_synth({"en": 0.5, "es": 0.8}), base_timed=True)
    pieces = 5
    n = int(CROSSFADE_S * SAMPLE_RATE)
    assert 0.010 <= CROSSFADE_S <= 0.020 and n == 360
    # three English pieces of 0.5 s and two Spanish of 0.8 s, four joins
    expected = 3 * int(0.5 * SAMPLE_RATE) + 2 * int(0.8 * SAMPLE_RATE) - (pieces - 1) * n
    assert len(out.audio) == expected and out.spans_applied == 2
    assert [t.text for t in out.tokens] == ["It", "is", "called", "La", "Calabiuza", ",", "in", "El", "Salvador", "."]
    times = [(t.start_s, t.end_s) for t in out.tokens if t.start_s is not None]
    assert all(a <= b for a, b in times) and all(times[i][0] <= times[i + 1][0] for i in range(len(times) - 1))
    assert max(e for _, e in times) <= len(out.audio) / SAMPLE_RATE + 1e-9


def test_foreign_words_keep_the_mapper_in_step_but_are_unaligned():
    from word_mapper import map_words

    out = splice_sentence(SENTENCE, SPANS, "en", fake_synth({"en": 0.5, "es": 0.8}), base_timed=True)
    mapped = map_words(SENTENCE.split(), out.tokens)
    flags = [m.aligned for m in mapped]
    assert flags == [True, True, True, False, False, True, False, False]  # It is called | La Calabiuza, | in | El Salvador.


def test_crossfade_blends_the_join_and_levels_are_matched():
    a, b = np.full(2400, 0.1, dtype=np.float32), np.full(2400, 0.3, dtype=np.float32)
    joined, starts = join([a, b])
    n = int(CROSSFADE_S * SAMPLE_RATE)
    assert len(joined) == 4800 - n and starts == [0.0, (2400 - n) / SAMPLE_RATE]
    seam = joined[2400 - n:2400]
    assert seam[0] == pytest.approx(0.1, abs=0.01) and seam[-1] == pytest.approx(0.3, abs=0.01)
    out = splice_sentence(SENTENCE, SPANS, "en", fake_synth({"en": 0.5, "es": 0.8}), base_timed=True)
    mid_en, mid_es = out.audio[SAMPLE_RATE // 8], out.audio[int(0.5 * SAMPLE_RATE) + SAMPLE_RATE // 4]
    assert abs(mid_es - mid_en) < 0.1  # 0.1 vs 0.2 at the source: matched toward the median


def test_untimed_base_engine_leaves_timing_to_the_recognizer():
    out = splice_sentence(SENTENCE, SPANS, "en", fake_synth({"en": 0.5, "es": 0.8}, timed=False), base_timed=False)
    assert out.tokens == () and len(out.audio) > 0


def test_splice_with_only_empty_audio_returns_empty():
    empty = lambda lang, text: SentenceAudio(np.zeros(0, dtype=np.float32), ())  # noqa: E731
    assert splice_sentence(SENTENCE, SPANS, "en", empty, True).audio.size == 0


# ---- voice splice (the default for Polly): the other language's voice reads the foreign words -------------------------------------------------
class VoiceFake(FakePolly):
    """Records which voice each request used and returns word marks for plain text."""

    def synthesize_speech(self, **kw):
        self.calls.append(kw)
        if kw["OutputFormat"] == "pcm":
            return {"AudioStream": io.BytesIO(self.pcm)}
        words, cursor, marks = [w for w in kw["Text"].split() if any(c.isalnum() for c in w)], 0, []  # Polly marks words, never lone punctuation
        for n, word in enumerate(words):
            i = kw["Text"].index(word, cursor)
            marks.append({"time": n * 300, "type": "word", "start": i, "end": i + len(word), "value": word})
            cursor = i + len(word)
        return {"AudioStream": io.BytesIO("\n".join(json.dumps(m) for m in marks).encode())}


def spliced_engine(client):
    foreign = PollyEngine(client, voice="Lupe", engine="neural", language="es")
    return PollyEngine(client, voice="Joanna", engine="neural", language="en", foreign=foreign)


def test_the_foreign_words_are_read_by_the_other_languages_voice_not_by_a_language_tag(monkeypatch):
    monkeypatch.delenv("MIXED_LANGUAGE_POLLY", raising=False)
    client = VoiceFake()
    out = spliced_engine(client).synthesize(SENTENCE, spans=SPANS)
    voices = [(c["VoiceId"], c["Text"]) for c in client.calls if c["OutputFormat"] == "pcm"]
    assert ("Lupe", "La Calabiuza") in voices and ("Lupe", "El Salvador") in voices
    assert any(v == "Joanna" and t.startswith("It is called") for v, t in voices)
    assert all(c["TextType"] == "text" for c in client.calls), "no SSML tags in this mode"
    assert [t.text for t in out.tokens] == ["It", "is", "called", "La", "Calabiuza", "in", "El", "Salvador"]
    starts = [t.start_s for t in out.tokens]
    assert starts == sorted(starts) and all(s is not None for s in starts), "every word, foreign ones too, has its own time, in order"
    assert out.spans_applied == 2


def test_the_tag_mode_switch_brings_the_ssml_path_back(monkeypatch):
    monkeypatch.setenv("MIXED_LANGUAGE_POLLY", "tag")
    client = FakePolly(recorded_marks)
    spliced_engine(client).synthesize(SENTENCE, spans=SPANS)
    assert all(c["TextType"] == "ssml" for c in client.calls)


def test_a_failed_splice_falls_back_to_tags_instead_of_losing_the_sentence(monkeypatch):
    monkeypatch.delenv("MIXED_LANGUAGE_POLLY", raising=False)

    class Flaky(FakePolly):
        def synthesize_speech(self, **kw):
            if kw["TextType"] == "text" and kw["VoiceId"] == "Lupe":
                raise RuntimeError("Lupe is unavailable")
            return super().synthesize_speech(**kw)

    out = spliced_engine(Flaky(recorded_marks)).synthesize(SENTENCE, spans=SPANS)
    assert out.audio.size and out.spans_applied == 2


def test_a_sentence_without_foreign_words_is_read_by_the_base_voice_only():
    client = VoiceFake()
    spliced_engine(client).synthesize("It is a nice day.", spans=())
    assert {c["VoiceId"] for c in client.calls} == {"Joanna"}
