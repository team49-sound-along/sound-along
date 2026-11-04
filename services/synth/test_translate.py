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
    assert "Piedmont Park" not in sent and "Xq" in sent  # the model never sees a longer name (single words like Atlanta are left to the model)
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


def test_localised_place_names_are_restored_instead_of_the_original_and_reported():
    out = tr.translate_passage({"title": "", "content": "<p>We saw Great Britain.</p>"}, lambda xs: ["Vimos " + x.split()[-1] for x in xs], names_fn=lambda t: ["Great Britain"],
                               localize=lambda names: {"Great Britain": "Gran Bretaña"})
    assert "Gran Bretaña" in out.content_html and "Great Britain" not in out.content_html and out.localized == {"Great Britain": "Gran Bretaña"}


def test_a_failing_localiser_just_keeps_the_original_names():
    def boom(names):
        raise RuntimeError("offline")

    out = tr.translate_passage({"title": "", "content": "<p>We saw Great Britain.</p>"}, lambda xs: ["Vimos " + x.split()[-1] for x in xs], names_fn=lambda t: ["Great Britain"], localize=boom)
    assert "Great Britain" in out.content_html and out.localized == {}


def test_casual_english_is_written_out_in_full_for_young_readers():
    assert tr.plain_register("They're gonna eat. Gonna go? I wanna play and I gotta run.") == "They're going to eat. Going to go? I want to play and I have to run."
    assert tr.plain_register("The gonnas of the town") == "The gonnas of the town"  # whole words only
    assert tr.plain_register("Nothing to change here.") == "Nothing to change here."


def test_a_single_word_place_with_no_local_name_is_left_to_the_model_but_longer_names_stay_protected():
    model = FakeModel()
    out = tr.translate_passage({"title": "", "content": "<p>We saw Britain and Piedmont Park today.</p>"}, model, names_fn=lambda t: ["Britain", "Piedmont Park"], localize=lambda names: {})
    sent = model.calls[0][0]
    assert "Britain" in sent and "Piedmont Park" not in sent and "Xq" in sent
    assert "Piedmont Park" in out.content_html  # restored exactly
    model = FakeModel()
    tr.translate_passage({"title": "", "content": "<p>We saw Britain today.</p>"}, model, names_fn=lambda t: ["Britain"], localize=None)
    assert "Britain" in model.calls[0][0]  # the same when place lookups are switched off
    model = FakeModel()
    tr.translate_passage({"title": "", "content": "<p>We saw Britain today.</p>"}, model, names_fn=lambda t: ["Britain"], localize=lambda names: {"Britain": "Gran Bretaña"})
    assert "Britain" not in model.calls[0][0]  # a name that has a local form is protected, then restored in that form


def test_the_larger_model_is_used_only_for_short_english_to_spanish_passages(monkeypatch):
    monkeypatch.delenv("TRANSLATE_BIG", raising=False)
    assert tr.use_big("en", "es", 300) and tr.use_big("en", "es", tr.BIG_MAX_WORDS)
    assert not tr.use_big("en", "es", tr.BIG_MAX_WORDS + 1)  # long: the small model keeps Lambda inside its time limit
    assert not tr.use_big("es", "en", 100)  # no larger Spanish to English model exists
    assert not tr.use_big("en", "es", None) and not tr.use_big("en", "es", 0)
    monkeypatch.setenv("TRANSLATE_BIG", "off")
    assert not tr.use_big("en", "es", 300)


def test_the_larger_model_is_pinned_by_full_commit_hash():
    repo, revision = tr.BIG[("en", "es")]
    assert repo == "Helsinki-NLP/opus-mt-tc-big-en-es" and len(revision) == 40


def test_su_never_becomes_your_in_a_story_but_a_reader_is_still_addressed_as_you():
    assert tr.fix_possessive("El parque está cerca de su casa.", "The park is close to your house.") == "The park is close to their house."
    assert tr.fix_possessive("Usted debe traer su libro.", "You must bring your book.") == "You must bring your book."
    assert tr.fix_possessive("Tu casa es grande y su jardín también.", "Your house is big and your garden too.") == "Your house is big and your garden too."
    assert tr.fix_possessive("La casa es azul.", "The house is blue.") == "The house is blue."


def test_a_name_the_model_changed_in_one_sentence_is_restored_when_it_kept_it_in_another():
    src = ["Los sábados, Ana y su hermano Pablo van al parque.", "Primero, Pablo corre hasta el columpio.", "Hoy Pablo quiere jugar."]
    out = ["On Saturdays, Ana and her brother Pablo go to the park.", "First, Paul runs to the swing.", "Today Pablo wants to play."]
    assert tr.restore_names(src, out)[1] == "First, Pablo runs to the swing."


def test_names_are_left_alone_when_there_is_no_evidence_or_the_change_is_ambiguous():
    src = ["Pedro y Lucía llegaron tarde.", "Luego Pedro se fue."]
    out = ["Peter and Lucia were late.", "Then Peter left."]
    assert tr.restore_names(src, out) == out  # changed everywhere: consistent, so untouched
    src = ["Vivimos en Estados Unidos.", "Visitamos Estados Unidos hoy."]
    out = ["We live in United States.", "We visited United States today."]
    assert tr.restore_names(src, out) == out
    src = ["Ana vio a Pablo con Lucía.", "Hoy Pablo y Lucía comen."]
    out = ["Ana saw Pablo with Lucia.", "Today Pablo and Lucia eat."]
    assert tr.restore_names(src, out)[0] == out[0]  # two names, one vanished and one new word: too ambiguous to fix
