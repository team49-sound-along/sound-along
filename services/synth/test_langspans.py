"""Mixed-language span detection: what must switch voice and, just as important, what must not."""
import os
import time

import pytest

import langspans as ls
from langspans import Span, detect_spans

PASSAGE = (
    "...a special tradition happens in El Salvador. It is called La Calabiuza (kah-laa-bee-YOO-zah). "
    "La Calabiuza is a night when families gather. The Maya, the Lenca, and Pipil all have called El Salvador home. "
    "In the 1500s, Spanish explorers came to El Salvador. Indigenous traditions blended with Spanish ones."
)


def texts(text, base="en"):
    return [text[s.start:s.end] for s in detect_spans(text, base)]


@pytest.fixture(autouse=True)
def _feature_on(monkeypatch):
    monkeypatch.delenv("MIXED_LANGUAGE", raising=False)


# ---- the motivating passage
def test_el_salvador_passage_exact_spans():
    expected = []
    pos = 0
    for needle in ["El Salvador", "La Calabiuza", "La Calabiuza", "El Salvador", "El Salvador"]:
        i = PASSAGE.index(needle, pos)
        expected.append(Span(i, i + len(needle), "es"))
        pos = i + len(needle)
    assert detect_spans(PASSAGE, "en") == expected


def test_passage_leaves_english_and_indigenous_names_alone():
    got = texts(PASSAGE)
    for word in ("Spanish", "Maya", "Lenca", "Pipil", "Indigenous"):
        assert not any(word in g for g in got)


def test_respelling_in_parentheses_is_untouched():
    t = "It is called La Calabiuza (kah-laa-bee-YOO-zah)."
    assert texts(t) == ["La Calabiuza"]
    assert detect_spans(t, "en")[0].end == t.index(" (")


def test_bare_respelling_is_untouched():
    assert texts("Say kah-laa-bee-YOO-zah slowly.") == []
    assert texts("Say WAH-kah-MOH-leh and then la-LOH-ron.") == []


def test_respelling_after_phrase_is_masked():
    t = "We celebrate Día de los Muertos (DEE-ah deh lohs MWAYR-tohs) in November."
    assert texts(t) == ["Día de los Muertos"]


# ---- place names: Spanish-speaking countries switch, anglicised US names do not
@pytest.mark.parametrize("t", [
    "We flew to Los Angeles last week.",
    "San Francisco, Las Vegas, El Paso and Santa Fe are cities.",
    "Colorado, Florida, California and Nevada are states.",
    "She moved from El Paso to Las Cruces.",
    "Mexico, Peru and Chile are countries.",
    "He ate at Del Taco near Del Mar.",
    "Santa Claus came to town.",
])
def test_anglicised_names_stay_english(t):
    assert texts(t) == []


@pytest.mark.parametrize("t,expected", [
    ("I love Guatemala. Honduras is next.", ["Guatemala", "Honduras"]),
    ("We visited Buenos Aires in May.", ["Buenos Aires"]),
    ("Nicaragua is north of Costa Rica.", ["Nicaragua", "Costa Rica"]),
    ("We flew to San José, Costa Rica, last spring.", ["San José, Costa Rica"]),
    ("The Los Ángeles basin is large.", ["Los Ángeles"]),
])
def test_spanish_places_switch(t, expected):
    assert texts(t) == expected


def test_possessive_suffix_is_not_in_span():
    t = "El Salvador's coast is long."
    assert texts(t) == ["El Salvador"]


# ---- words and phrases
@pytest.mark.parametrize("t,expected", [
    ("My abuela made empanadas", ["abuela", "empanadas"]),
    ("She broke the piñata at her quinceañera.", ["piñata", "quinceañera"]),
    ("Have you heard of La Llorona?", ["La Llorona"]),
    ("We celebrate Día de los Muertos every November.", ["Día de los Muertos"]),
    ("The word niño means boy.", ["niño"]),
    ("Mr. Muñoz lives here.", ["Muñoz"]),
    ("Goodnight, mi amor.", ["mi amor"]),
    ("He ate a pan dulce.", ["pan dulce"]),
    ("Marta said gracias.", ["gracias"]),
    ("Gracias, abuela.", ["Gracias, abuela"]),
    ('He said "hola" and left.', ["hola"]),
    ("I love El Salvador, La Calabiuza and Guatemala.", ["El Salvador, La Calabiuza", "Guatemala"]),
])
def test_spanish_words_and_phrases(t, expected):
    assert texts(t) == expected


# ---- quotes
def test_spanish_sentence_inside_straight_quotes():
    t = 'She said, "Buenos días, mi amor."'
    assert texts(t) == ["Buenos días, mi amor"]


def test_spanish_sentence_inside_curly_quotes():
    t = "She smiled and said, “Buenos días, mi amor.” Then she left."
    assert texts(t) == ["Buenos días, mi amor"]


def test_quote_with_unknown_word_is_covered_whole():
    t = 'She asked, "¿Dónde está la biblioteca?"'
    assert texts(t) == ["Dónde está la biblioteca"]


def test_inverted_marks_not_in_span():
    t = 'He asked, "¿Cómo estás?"'
    assert texts(t) == ["Cómo estás"]


def test_quote_sentences_are_separate_spans():
    t = 'She said, "Hola. Buenos días."'
    assert texts(t) == ["Hola", "Buenos días"]


def test_sung_quote():
    assert texts('We sang "Feliz cumpleaños" to Mom.') == ["Feliz cumpleaños"]


# ---- boundaries
def test_never_spans_sentence_end():
    t = "I saw Costa Rica. El Salvador is next. Then Honduras!"
    assert texts(t) == ["Costa Rica", "El Salvador", "Honduras"]


def test_newline_breaks_span():
    assert texts("El Salvador\nLa Calabiuza") == ["El Salvador", "La Calabiuza"]


def test_spans_are_whole_words_sorted_and_disjoint():
    for t in (PASSAGE, "Hola, abuela! Mi amor, piñata? Costa Rica's niño.", 'x "Buenos días, mi amor." y'):
        spans = detect_spans(t, "en")
        for a, b in zip(spans, spans[1:]):
            assert a.end <= b.start
        for s in spans:
            assert s.start < s.end
            assert s.start == 0 or not t[s.start - 1].isalnum()
            assert s.end == len(t) or not t[s.end].isalnum()
            assert s.lang == "es"


# ---- conservative: ambiguous or ordinary things
def test_ambiguous_single_words_do_not_switch():
    t = "In the original sin, no one could pan for gold, and to me the sale was real."
    assert texts(t) == []


def test_accented_loanwords_alone_do_not_switch():
    assert texts("The café opened. He read the résumé. A jalapeño pepper.") == []


def test_acronyms_and_all_caps_ignored():
    assert texts("The UN met in Geneva.") == []
    assert texts("EL SALVADOR") == []


def test_single_accent_name_alone_does_not_switch():
    assert texts("Her name is Ángel.") == []


# ---- Spanish passages with English
def test_spanish_base_halloween_and_thanksgiving():
    t = "Mi hermana ama el Halloween y el Thanksgiving."
    assert texts(t, "es") == ["Halloween", "Thanksgiving"]
    assert all(s.lang == "en" for s in detect_spans(t, "es"))


def test_spanish_base_phrase_and_names():
    assert texts("Celebramos Thanksgiving Day en noviembre.", "es") == ["Thanksgiving Day"]
    assert texts("Vivimos en New York desde 2010.", "es") == ["New York"]
    assert texts("The Beatles tocaron aquí.", "es") == ["The Beatles"]
    assert texts("Mi mamá mira Netflix.", "es") == ["Netflix"]


def test_spanish_base_english_quote():
    t = 'Ella dijo: "Happy birthday to you."'
    assert texts(t, "es") == ["Happy birthday to you"]


def test_spanish_base_plain_spanish_and_names_unchanged():
    assert texts("Michael y Sarah fueron al parque con Brown.", "es") == []
    assert texts("La casa es grande, y el perro come pan.", "es") == []


def test_spanish_text_with_spanish_base_has_no_spanish_spans():
    assert texts("Buenos días, mi amor. El Salvador es bonito.", "es") == []


# ---- robustness
@pytest.mark.parametrize("bad", [None, "", "   ", 42, b"El Salvador", [], "\x00\x00"])
def test_odd_input_never_raises(bad):
    assert detect_spans(bad, "en") == []


@pytest.mark.parametrize("base", [None, "", "fr", 7, "xx"])
def test_unknown_base_lang_is_empty(base):
    assert detect_spans("We visited El Salvador.", base) == []


def test_base_lang_variants_accepted():
    assert texts("We visited El Salvador.", "EN") == ["El Salvador"]
    assert texts("We visited El Salvador.", "en-US") == ["El Salvador"]


def test_emoji_and_unicode_offsets():
    t = "\U0001F600\U0001F600 We love El Salvador \U0001F600 and niño"
    got = detect_spans(t, "en")
    assert [t[s.start:s.end] for s in got] == ["El Salvador", "niño"]


def test_decomposed_accents_work():
    t = "We celebrate Día de los Muertos."
    assert texts(t) == ["Día de los Muertos"]


def test_long_degenerate_inputs_are_fast():
    for t in ("a" * 1_000_000, "(" * 200_000, "((a))" * 100_000, "-".join(["ab"] * 100_000), '"' * 100_000):
        start = time.perf_counter()
        detect_spans(t, "en")
        assert time.perf_counter() - start < 2.0


def test_twelve_thousand_words_under_a_second():
    unit = ("The family walked to El Salvador market and bought pan, sale items and real fruit. "
            "My abuela said hola and we ate empanadas. She said, \"Buenos días, mi amor.\" ")
    text = unit * 500  # about 12,000 words
    assert len(text.split()) >= 12_000
    start = time.perf_counter()
    spans = detect_spans(text, "en")
    assert time.perf_counter() - start < 1.0
    assert len(spans) >= 2000
    start = time.perf_counter()
    detect_spans(("Mi hermana ama el Halloween y la casa es grande. " * 1200), "es")
    assert time.perf_counter() - start < 1.0


# ---- switch and determinism
@pytest.mark.parametrize("value", ["off", "OFF", " Off ", "0", "false", "no"])
def test_mixed_language_off_returns_empty(monkeypatch, value):
    monkeypatch.setenv("MIXED_LANGUAGE", value)
    assert detect_spans(PASSAGE, "en") == []
    assert ls.mixed_language_enabled() is False


def test_mixed_language_on_values(monkeypatch):
    monkeypatch.setenv("MIXED_LANGUAGE", "on")
    assert len(detect_spans(PASSAGE, "en")) == 5
    assert ls.mixed_language_enabled() is True


def test_deterministic():
    runs = [detect_spans(PASSAGE, "en") for _ in range(5)]
    assert all(r == runs[0] for r in runs)


def test_span_is_frozen():
    s = Span(0, 1, "es")
    with pytest.raises(Exception):
        s.start = 5  # type: ignore[misc]
