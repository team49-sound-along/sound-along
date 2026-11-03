"""Passage translation (English <-> Spanish): sentence by sentence, place names protected, an explicit sentence map. No model needed here."""
import pytest

import translate as tr
from pipeline import tokenize_html

HTML = ("<p>Lots of people live in big cities. They can go to a park!</p>"
        "<p>In Atlanta, Georgia, there's a big park called Piedmont Park. Over six million people visit it every year!</p>")


class FakeModel:
    """Stands in for the translator: 'translates' by upper-casing common words and keeping unknown capitalised tokens (placeholders) as they are."""

    def __init__(self, drop_placeholders=False, split=None):
        self.calls, self.drop, self.split = [], drop_placeholders, split or {}

    def __call__(self, texts):
        self.calls.append(list(texts))
        out = []
        for t in texts:
            t = t.replace("Xq", "Zz") if self.drop and "Xq" in t else t  # a model that mangles the placeholders
            out.append(self.split.get(t, "ES " + t))
        return out


def names(text):
    return ["Piedmont Park", "Atlanta", "Georgia"]


def run(model, html=HTML, **kw):
    return tr.translate_passage({"title": "Park", "content": html}, model, names_fn=names, **kw)


def test_each_sentence_is_translated_on_its_own_and_paragraphs_are_kept():
    out = run(FakeModel())
    assert out.content_html.count("<p>") == 2 and out.content_html.startswith("<p>ES Lots of people live in big cities.")
    assert len(tokenize_html(out.content_html)) > 10 and out.title == "ES Park"
    assert out.sentence_map == [[0], [1], [2], [3]]


def test_place_names_are_masked_before_translation_and_restored_exactly_after():
    model = FakeModel()
    out = run(model)
    sent = [t for batch in model.calls for t in batch if "park called" in t][0]
    assert "Piedmont Park" not in sent and "Atlanta" not in sent and "Xq" in sent  # the model never sees the real names
    assert "ES In Atlanta, Georgia, there's a big park called Piedmont Park." in out.content_html and out.unprotected == []


def test_if_a_model_loses_a_placeholder_the_sentence_is_retranslated_unmasked_and_the_loss_is_recorded():
    out = run(FakeModel(drop_placeholders=True))
    assert "Piedmont Park" in out.content_html  # never shipped with a broken name
    assert out.unprotected and all(isinstance(n, int) for n in out.unprotected)  # the sentence numbers that could not be protected


def test_a_translated_sentence_without_end_punctuation_gets_one_so_sentence_numbers_stay_stable():
    model = FakeModel(split={"Lots of people live in big cities.": "Mucha gente vive en ciudades"})
    out = run(model)
    assert "Mucha gente vive en ciudades." in out.content_html and out.sentence_map == [[0], [1], [2], [3]]


def test_when_a_translation_splits_into_two_sentences_the_map_says_so():
    model = FakeModel(split={"They can go to a park!": "Pueden ir. A un parque!"})
    out = run(model)
    assert out.sentence_map == [[0], [1, 2], [3], [4]]
    assert len({t.sentence for t in tokenize_html(out.content_html)}) == 5


def test_the_sentence_map_is_checked_against_the_final_text():
    out = run(FakeModel())
    flat = [i for group in out.sentence_map for i in group]
    assert flat == list(range(len({t.sentence for t in tokenize_html(out.content_html)})))


def test_a_passage_with_no_readable_text_is_refused():
    with pytest.raises(ValueError, match="no readable text"):
        tr.translate_passage({"title": "T", "content": "<p>   </p>"}, FakeModel(), names_fn=names)


def test_placeholders_never_collide_with_real_words_and_cover_many_names():
    masked, table = tr.mask("A B C D E F G H I J K L M N O P Q R S T U V W X Y Z AA", [f"Name{i}" for i in range(30)])
    assert masked == "A B C D E F G H I J K L M N O P Q R S T U V W X Y Z AA" and table == {}
    names30 = [f"Place{c}{d}" for c in "abc" for d in "abcdefghij"]
    masked, table = tr.mask(" ".join(names30), names30)
    assert len(table) == 30 and len(set(table)) == 30 and all(p.startswith("Xq") and p.endswith("x") for p in table)
    assert tr.unmask(masked, table) == " ".join(names30)


def test_longer_names_are_masked_first_so_a_name_inside_a_name_is_not_split():
    masked, table = tr.mask("Boston Harbor is in Boston.", ["Boston", "Boston Harbor"])
    assert len(table) == 2 and list(table.values())[0] == "Boston Harbor"
    assert tr.unmask(masked, table) == "Boston Harbor is in Boston."


def test_only_whole_words_are_masked():
    masked, table = tr.mask("Chinatown and China.", ["China"])
    assert "Chinatown" in masked and list(table.values()) == ["China"]


def test_language_pairs_are_pinned_and_unknown_pairs_refused():
    assert set(tr.PAIRS) == {("en", "es"), ("es", "en")}
    assert all(len(rev) == 40 for _, rev in tr.PAIRS.values())
    with pytest.raises(ValueError, match="en to es or es to en"):
        tr.load_model("en", "fr")


def test_the_real_model_keeps_place_names_in_a_real_passage():
    pytest.importorskip("transformers")
    pytest.importorskip("sentencepiece")
    try:
        model = tr.load_model("en", "es")
    except Exception as err:  # noqa: BLE001 (not downloaded / offline)
        pytest.skip(f"model not available: {err}")
    out = tr.translate_passage({"title": "Park", "content": HTML}, model, names_fn=names)
    assert "Piedmont Park" in out.content_html and "Atlanta" in out.content_html and out.unprotected == []
    assert "parque" in out.content_html.lower()
