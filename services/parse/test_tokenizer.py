import json
from pathlib import Path

from tokenizer import sentences, tokenize_html

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def test_skips_figures_and_captions():
    html = '<figure><figcaption><p>Jill Lauren</p></figcaption></figure><p>Hello world.</p>'
    assert [t.text for t in tokenize_html(html)] == ["Hello", "world."]


def test_keeps_vocab_ids_across_punctuation():
    html = '<p>enjoy <span data-vocab-sense-id="42">nature</span>. Next.</p>'
    tokens = tokenize_html(html)
    assert [t.text for t in tokens] == ["enjoy", "nature.", "Next."]
    assert tokens[1].vocab_sense_id == "42"
    assert tokens[0].vocab_sense_id is None


def test_abbreviations_do_not_end_sentences():
    tokens = tokenize_html("<p>Ms. Lee met Dr. Kim. They left!</p>")
    assert len({t.sentence for t in tokens}) == 2


def test_indexes_are_stable_and_contiguous():
    tokens = tokenize_html("<p>One two.</p><p>Three four.</p>")
    assert [t.i for t in tokens] == [0, 1, 2, 3]
    assert tokens[1].sentence != tokens[2].sentence  # new paragraph, new sentence
    assert tokens[2].paragraph == 1


def test_sample_passage_round_trip():
    passage = json.loads((SAMPLES / "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98.json").read_text())
    tokens = tokenize_html(passage["content"])
    assert tokens[0].text == "Lots"
    assert "Jill" not in {t.text for t in tokens}  # image credit skipped
    assert any(t.vocab_sense_id for t in tokens)
    assert 340 <= len(tokens) <= 400  # ReadWorks lists 379 words for this passage; captions and credits are skipped
    assert len(sentences(tokens)) > 5


def test_em_dash_splits_joined_words_and_keeps_dash_on_the_first():
    tokens = tokenize_html("<p>It was good—and fun. Wait–what?</p>")
    assert [t.text for t in tokens] == ["It", "was", "good—", "and", "fun.", "Wait–", "what?"]
    assert [t.i for t in tokens] == list(range(7))


def test_em_dash_keeps_vocab_id_on_the_right_part():
    html = '<p>a <span data-vocab-sense-id="7">levied</span>—after b.</p>'
    tokens = tokenize_html(html)
    by_text = {t.text: t.vocab_sense_id for t in tokens}
    assert by_text["levied—"] == "7" and by_text["after"] is None


def test_dash_at_word_edges_is_not_split():
    tokens = tokenize_html("<p>—hello there— ok</p>")
    assert [t.text for t in tokens] == ["—hello", "there—", "ok"]


def _sentence_texts(html):
    out = {}
    for t in tokenize_html(html):
        out.setdefault(t.sentence, []).append(t.text)
    return [" ".join(v) for _, v in sorted(out.items())]


def test_a_dialogue_tag_stays_with_its_quote():
    assert _sentence_texts('<p>"Why?" she asked. "Fine!" he said. Then they left.</p>') == ['"Why?" she asked.', '"Fine!" he said.', "Then they left."]
    assert _sentence_texts("<p>—¿Cómo estás? —preguntó Luis. Muy bien.</p>") == ["—¿Cómo estás? —preguntó Luis.", "Muy bien."]


def test_dotted_abbreviations_and_titles_do_not_split_but_a_capital_after_them_does():
    assert _sentence_texts("<p>We met at 5 p.m. on Monday. Prof. Jones came on Jan. 3. Then we left.</p>") == ["We met at 5 p.m. on Monday.", "Prof. Jones came on Jan. 3.", "Then we left."]
    assert _sentence_texts("<p>We left at 5 p.m. We ate.</p>") == ["We left at 5 p.m.", "We ate."]
    assert _sentence_texts("<p>Son las 5 p. m. del jueves. Viven en EE. UU. y Canadá. Fin.</p>") == ["Son las 5 p. m. del jueves.", "Viven en EE. UU. y Canadá.", "Fin."]


def test_etc_ends_a_sentence_only_before_a_capital():
    assert _sentence_texts("<p>We bought apples, pears, etc. and left. We ate, etc. Then slept.</p>") == ["We bought apples, pears, etc. and left.", "We ate, etc.", "Then slept."]


def test_all_lowercase_text_still_splits_at_full_stops():
    assert _sentence_texts("<p>we went home. we ate dinner. it was good.</p>") == ["we went home.", "we ate dinner.", "it was good."]


def test_a_word_split_at_a_dash_remembers_that_no_space_followed_the_dash():
    tokens = tokenize_html("<p>It was good—and fun. Wait – what? 1990–1991 ok</p>")
    by_text = {t.text: t for t in tokens}
    assert by_text["and"].joined is True and by_text["1991"].joined is True
    assert by_text["good—"].joined is False and by_text["what?"].joined is False
    assert by_text["and"].to_dict()["join"] is True and "join" not in by_text["good—"].to_dict()


# ---- hostile text must not stall the tokenizer (linear time, not quadratic) ------------------------------------------------------------
import time as _time


def test_long_runs_of_punctuation_dots_and_closers_do_not_stall_the_tokenizer():
    cases = ["." * 200000 + "x", "?" * 200000 + "x", "a." * 100000 + " b", "a." + '"' * 200000, "a -- " * 60000, "x. " * 60000, "a" * 200000, " " * 300000 + "b."]
    for text in cases:
        started = _time.perf_counter()
        tokenize_html("<p>" + text + "</p>")
        assert _time.perf_counter() - started < 2.0, f"slow on {text[:12]!r}"


def test_sentence_ends_are_unchanged_by_the_linear_rewrite():
    tokens = tokenize_html('<p>Dr. Smith left at 5 p.m. on Monday. "Why?" she asked. It was fine.) Then U.S.A. won! Fin.</p>')
    sentence_of = {t.text: t.sentence for t in tokens}
    assert sentence_of["Smith"] == sentence_of["Dr."] and sentence_of["on"] == sentence_of["p.m."]  # abbreviations do not end a sentence
    assert sentence_of["she"] == sentence_of['"Why?"']  # a dialogue tag continues it
    assert sentence_of["Then"] != sentence_of["fine.)"] and sentence_of["Fin."] != sentence_of["won!"]
