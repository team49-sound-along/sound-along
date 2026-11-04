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
    assert tr.use_big("es", "en", 100) and not tr.use_big("es", "en", tr.BIG_MAX_WORDS + 1)  # Spanish to English has a larger model too
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


def test_spanish_questions_and_exclamations_get_their_opening_marks():
    assert tr.add_spanish_marks("para su gran deleite, ¡encajaba!") == "para su gran deleite, ¡encajaba!"  # already has one
    assert tr.add_spanish_marks("Cómo estás?") == "¿Cómo estás?"
    assert tr.add_spanish_marks("Qué bien!") == "¡Qué bien!"
    assert tr.add_spanish_marks('"Qué bien!" dijo ella.') == '"Qué bien!" dijo ella.'  # the sentence does not end with the mark
    assert tr.add_spanish_marks("—Cómo estás?") == "—¿Cómo estás?"
    assert tr.add_spanish_marks("Hola.") == "Hola."


class TruncatingModel:
    """Like the real model on long input: after 40 words it silently stops. Short input is translated word for word."""

    def __init__(self):
        self.calls = []

    def __call__(self, texts):
        self.calls.append(list(texts))
        return ["ES " + " ".join(t.split()[:40]) + ("." if t.rstrip().endswith(".") else "") for t in texts]


def _long_sentence(n=100):
    return ", ".join(" ".join(f"w{j}" for j in range(i * 9, i * 9 + 9)) for i in range(n // 9 + 1)) + "."


def test_a_long_sentence_is_translated_in_pieces_so_nothing_is_cut_off():
    model = TruncatingModel()
    sentence = _long_sentence(100)
    out = tr.translate_passage({"title": "", "content": f"<p>{sentence}</p>"}, model, names_fn=lambda t: [])
    text = out.content_html
    assert "w99" in text and "w0" in text, "the end of the sentence must survive"
    assert max(len(call) for call in model.calls) >= 2 and all(len(t.split()) <= tr.PIECE_WORDS + 2 for call in model.calls for t in call)
    assert out.sentence_map == [[0]]


def test_pieces_are_cut_at_punctuation_and_a_stretch_without_any_is_cut_by_words():
    pieces = tr.split_pieces("a b c, d e f; g h i: j k l", 4)
    assert pieces == ["a b c,", "d e f;", "g h i:", "j k l"]
    assert all(len(p.split()) <= 14 for p in tr.split_pieces(" ".join(f"x{i}" for i in range(60)), 14))
    assert " ".join(tr.split_pieces(" ".join(f"x{i}" for i in range(60)), 14)).split() == [f"x{i}" for i in range(60)]


def test_a_piece_goes_back_into_the_sentence_with_a_lowercase_start_and_no_full_stop():
    assert tr._fit_piece("when suddenly a rabbit,", "Cuando de repente un conejo.", first=False, last=False) == "cuando de repente un conejo"
    assert tr._fit_piece("Alice was tired,", "Alice estaba cansada,", first=True, last=False) == "Alice estaba cansada,"
    assert tr._fit_piece("and she left.", "Y se fue.", first=False, last=True) == "y se fue."


def test_a_translation_of_an_impossible_length_is_retried_in_smaller_pieces():
    class DropsMost:
        def __init__(self):
            self.n = 0

        def __call__(self, texts):
            self.n += 1
            return [("short" if len(t.split()) > 30 else "ES " + t) for t in texts]

    model = DropsMost()
    sentence = " ".join(f"p{i}" for i in range(30)) + " ok."  # 31 words: not long, but the model returns 1 word
    got = tr._translate_all([sentence], model)[0]
    assert len(got.split()) >= 0.55 * 31, got


def test_short_sentences_still_go_through_in_batches_as_before():
    model = FakeModel()
    tr._translate_all(["One two three."] * 20, model)
    assert [len(c) for c in model.calls] == [16, 4]


def test_a_paragraph_that_ends_with_a_semicolon_keeps_it_instead_of_gaining_a_full_stop():
    out = tr.translate_passage({"title": "", "content": "<p>First part; second part;</p><p>Next paragraph here.</p>"}, FakeModel(), names_fn=lambda t: [])
    assert ";." not in out.content_html and "second part;</p>" in out.content_html
    assert out.sentence_map == [[0], [1]]


def test_a_dropped_closing_quote_is_put_back():
    assert tr.balance_quotes("\u201CDo you want to help?\u201D Marta asked. \u201CI have to water the plants.") == "\u201CDo you want to help?\u201D Marta asked. \u201CI have to water the plants.\u201D"
    assert tr.balance_quotes('He said "wait.') == 'He said "wait."'
    assert tr.balance_quotes("\u201CHi,\u201D he said.") == "\u201CHi,\u201D he said."
    assert tr.balance_quotes("No quotes here.") == "No quotes here."


def test_both_larger_models_are_pinned_by_full_commit_hash():
    for pair in (("en", "es"), ("es", "en")):
        repo, revision = tr.BIG[pair]
        assert repo.startswith("Helsinki-NLP/opus-mt-tc-") and len(revision) == 40


def test_a_first_name_that_a_model_respelled_or_translated_is_put_back():
    assert tr.restore_translated_names(["Visitamos el parque con Ana.", "Lucía y Pedro llegaron tarde.", "El perro de Juan se escapó."], ["We visited the park with Anna.", "Lucia and Peter were late.", "John's dog ran away."]) == [
        "We visited the park with Ana.", "Lucía and Pedro were late.", "Juan's dog ran away."]


def test_names_are_left_alone_when_the_source_name_is_already_there_or_nothing_matches():
    assert tr.restore_translated_names(["Ana vio a Pedro."], ["Ana saw Pedro."]) == ["Ana saw Pedro."]
    assert tr.restore_translated_names(["Vimos un pájaro."], ["We saw a bird."]) == ["We saw a bird."]
    assert tr.restore_translated_names(["Pablo corre."], ["Paul's friend runs."])[0].startswith("Pablo")


def test_translating_a_passage_keeps_a_name_even_when_the_model_changes_it():
    class Respeller:
        def __call__(self, texts):
            return [t.replace("Ana", "Anna").replace("Lucía", "Lucy") for t in texts]

    out = tr.translate_passage({"title": "", "content": "<p>Visitamos el parque con Ana. Después vimos a Lucía.</p>"}, Respeller(), names_fn=lambda t: [])
    assert "Ana" in out.content_html and "Anna" not in out.content_html and "Lucía" in out.content_html and "Lucy" not in out.content_html


# ---- quoted speech with a tag ("..." asked Mia.) ------------------------------------------------------------------------------------
def test_split_speech_finds_the_quote_and_its_short_tag():
    assert tr.split_speech('"Where are you going?" asked Mia.') == ('"Where are you going?"', "asked Mia.")
    assert tr.split_speech("“To the lake,” said Tom.") == ("“To the lake,”", "said Tom.")
    assert tr.split_speech('"It was Mr. Brown\'s fault, not mine," Tom replied.') == ('"It was Mr. Brown\'s fault, not mine,"', "Tom replied.")
    assert tr.split_speech('"Hello." ') is None  # no tag
    assert tr.split_speech('He shouted "Look out!" and I jumped.') is None  # the quote is not first
    assert tr.split_speech('"Stop," he said, "or I will go."') is None  # a second quote


def test_speech_and_tag_are_translated_apart_so_the_dash_dialogue_of_the_model_never_glues_them():
    seen = []

    table = {"Where are you going?": "¿Adónde vas?", "asked Mia.": "Preguntó Mia."}

    def fake(texts):
        seen.extend(texts)
        return [table[x] for x in texts]

    out = tr._translate_all(['"Where are you going?" asked Mia.'], fake)
    assert out == ["\"¿Adónde vas?\" preguntó Mia."] and seen == ["Where are you going?", "asked Mia."]


def test_speech_keeps_its_capital_its_comma_and_a_named_speaker():
    table = {"To the lake,": "al lago,", "Tom replied.": "Tom respondió.", "said Tom.": "Dijo Tom."}
    out = tr._translate_all(['"To the lake," said Tom.', '"To the lake," Tom replied.'], lambda xs: [table[x] if x in table else {"To the lake": "al lago,"}[x] for x in xs])
    assert out == ['"Al lago," dijo Tom.', '"Al lago," Tom respondió.']


def test_tidy_spanish_fixes_what_the_model_gets_wrong_about_country_names_money_and_units():
    assert tr.tidy_spanish("el Estados Unidos pierde el 40%") == "Estados Unidos pierde el 40%"
    assert tr.tidy_spanish("viven en el Estados Unidos") == "viven en Estados Unidos"
    assert tr.tidy_spanish("del Estados Unidos") == "de Estados Unidos"
    assert tr.tidy_spanish("Cuesta menos de $ 5, y") == "Cuesta menos de $5, y"
    assert tr.tidy_spanish("60 libras. de miel") == "60 libras de miel"
    assert tr.tidy_spanish("Pesa 60 libras. Es mucho.") == "Pesa 60 libras. Es mucho."


def test_a_translated_passage_is_tidied_after_names_are_put_back():
    class M:
        def __call__(self, texts):
            return ["El Piedmont Park pierde 60 libras. de miel." if "Piedmont" in t else "x." for t in texts]

    out = tr.translate_passage({"title": "", "content": "<p>Piedmont Park loses 60 lbs. of honey.</p>"}, M(),
                               names_fn=lambda text: ["Piedmont Park"], localize=lambda ns: {"Piedmont Park": "Estados Unidos"})
    assert "el Estados" not in out.content_html.lower() and "60 libras de miel" in out.content_html
