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
