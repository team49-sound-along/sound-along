"""Validate samples/cards/*.cards.json against docs/CARDS.md and the passage the reader actually shows.

Words are checked against the REAL reader tokens (services/parse/tokenizer.py), not a raw-text substring, so "art" never
matches inside "start" and image captions (which the reader skips) do not count.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "parse"))
from tokenizer import tokenize_html  # noqa: E402

SAMPLES = ROOT / "samples"
CARDS = SAMPLES / "cards"
EXPECTED = (  # the three English texts (AI passage ids), see docs/BACKEND_HANDOFF.md
    "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98",
    "5af24980-4d6d-41c1-87fa-4f21cb2d169d",
    "ff1d34c9-14f1-4e78-b509-6568dc912a17",
)
POS = {"noun", "verb", "adjective", "adverb"}
WORD_FIELDS = {"word", "syllables", "ipa", "partOfSpeech", "definition", "example", "spanish"}
PLACE_FIELDS = {"name", "summary", "attribution", "imageUrl", "imageAlt", "imageCredit"}


def word_key(text: str) -> str:
    """Python twin of wordKey in web/src/cards.js: lower case, edge punctuation removed, inner apostrophes kept."""
    chars = list(str(text).lower())
    while chars and not chars[0].isalnum():
        chars.pop(0)
    while chars and not chars[-1].isalnum():
        chars.pop()
    return "".join(chars)


def norm(text: str) -> str:
    """Whitespace and quote normalisation so a sentence can be compared with the reader's text."""
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(text.split()).lower()


def load(passage_id: str):
    passage = json.loads((SAMPLES / f"{passage_id}.json").read_text(encoding="utf-8"))
    tokens = tokenize_html(passage["content"])
    plain = norm(" ".join(t.text for t in tokens))
    return passage, tokens, plain


def card_files() -> list[Path]:
    return sorted(CARDS.glob("*.cards.json"))


def read_cards(passage_id: str) -> dict:
    return json.loads((CARDS / f"{passage_id}.cards.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("passage_id", EXPECTED)
def test_every_english_text_has_a_cards_file(passage_id: str) -> None:
    assert (CARDS / f"{passage_id}.cards.json").is_file(), f"samples/cards/{passage_id}.cards.json is missing"


def test_there_are_no_stray_cards_files() -> None:
    assert {p.name for p in card_files()} <= {f"{i}.cards.json" for i in EXPECTED}


@pytest.fixture(params=EXPECTED)
def doc(request):
    passage_id = request.param
    if not (CARDS / f"{passage_id}.cards.json").is_file():
        pytest.skip("covered by test_every_english_text_has_a_cards_file")
    passage, tokens, plain = load(passage_id)
    return passage_id, passage, tokens, plain, read_cards(passage_id)


def test_shape_is_exactly_the_contract(doc) -> None:
    _, _, _, _, cards = doc
    assert set(cards) == {"words", "places"}
    for key, card in cards["words"].items():
        assert set(card) == WORD_FIELDS, key
        assert card["partOfSpeech"] in POS, key
        assert isinstance(card["definition"], str) and card["definition"].strip(), key
    for key, card in cards["places"].items():
        assert set(card) == PLACE_FIELDS, key
        assert card["name"] == key, key


def test_word_keys_are_normalised_and_are_words_the_reader_shows(doc) -> None:
    _, _, tokens, _, cards = doc
    shown = {word_key(t.text) for t in tokens}
    for key, card in cards["words"].items():
        assert key == word_key(key), f"{key!r} is not in normalised form"
        assert card["word"] == key, f"{key!r}: card.word must equal the key"
        assert key in shown, f"{key!r} is not a word in the passage as the reader shows it"


def test_every_vocabulary_word_in_the_text_has_a_card(doc) -> None:
    """Tokens carry vocabId; a tap on any form ("colonists", "taxed") must find a card, not just the lemma."""
    _, _, tokens, _, cards = doc
    missing = sorted({word_key(t.text) for t in tokens if t.vocab_sense_id} - set(cards["words"]))
    assert not missing, f"vocabulary words without a card: {missing}"


def test_spanish_and_syllables(doc) -> None:
    _, _, _, _, cards = doc
    for key, card in cards["words"].items():
        assert isinstance(card["spanish"], list) and all(isinstance(s, str) and s.strip() for s in card["spanish"]), key
        if card["syllables"] is not None:
            assert card["syllables"].replace("·", "") == key, f"{key}: syllables must spell the word"
        assert card["ipa"] is None or re.fullmatch(r"/[^/\s]+/", card["ipa"]), f"{key}: ipa must be /.../ or null"


def test_plain_text_only_and_length_limits(doc) -> None:
    _, _, _, _, cards = doc
    strings = []
    for key, card in cards["words"].items():
        assert len(card["definition"]) <= 140, f"{key}: definition over 140 characters"
        strings += [card["definition"], card["example"] or "", card["syllables"] or "", card["ipa"] or "", *card["spanish"]]
    for key, card in cards["places"].items():
        assert len(card["summary"]) <= 160, f"{key}: summary over 160 characters"
        strings += [card["summary"], card["attribution"], card["name"]]
    for card in cards["places"].values():
        strings += [card["imageAlt"] or "", card["imageCredit"] or ""]
    for text in strings:
        assert not re.search(r"[<>]|https?:|www\.", text), f"markup or link in {text!r}"


def test_an_example_is_a_real_sentence_of_the_passage(doc) -> None:
    _, _, _, plain, cards = doc
    for key, card in cards["words"].items():
        if card["example"] is not None:
            assert norm(card["example"]) in plain, f"{key}: example is not a sentence of the passage: {card['example']!r}"


def test_places_appear_in_the_text_and_credit_wikipedia(doc) -> None:
    _, _, _, plain, cards = doc
    for key, card in cards["places"].items():
        assert re.search(rf"(?<![\w]){re.escape(norm(key))}(?![\w])", plain), f"place {key!r} is not in the passage"
        assert "CC BY-SA" in card["attribution"], key
        assert card["summary"].strip(), key


def test_a_place_picture_is_a_small_real_image_on_our_own_origin_with_alt_text_and_a_credit(doc) -> None:
    import place_images as pi

    _, _, _, _, cards = doc
    for key, card in cards["places"].items():
        if card["imageUrl"] is None:
            assert card["imageAlt"] is None and card["imageCredit"] is None, f"{key}: alt and credit without a picture"
            continue
        name = card["imageUrl"].removeprefix("/data/")
        assert card["imageUrl"].startswith("/data/") and pi.NAME_PATTERN.fullmatch(name), f"{key}: imageUrl must be /data/<uuid>.place-<slug>-<hash>.jpg|png, never an absolute URL"
        data = (CARDS / "images" / name).read_bytes()
        assert pi.image_ext(data) == name.rsplit(".", 1)[1], f"{key}: file is not really a {name.rsplit('.', 1)[1]}"
        assert len(data) <= 150_000, f"{key}: {len(data)} bytes is over the 150 KB budget"
        assert name.split("-")[-1].split(".")[0] == pi.hashlib.sha256(data).hexdigest()[:8], f"{key}: file name hash does not match the content"
        assert pi.alt_problem(card["imageAlt"], key) is None, f"{key}: {pi.alt_problem(card['imageAlt'], key)}"
        assert any(lic in card["imageCredit"] for lic in ("CC BY", "CC0", "Public domain")), f"{key}: credit must name the licence"
        assert "Wikimedia Commons" in card["imageCredit"] and "http" not in card["imageCredit"]


def test_there_are_no_orphan_image_files(doc) -> None:
    _, _, _, _, cards = doc
    used = {c["imageUrl"].removeprefix("/data/") for c in cards["places"].values() if c["imageUrl"]}
    own = {p.name for p in (CARDS / "images").glob(f"{doc[0]}.place-*")}
    assert own == used, f"image files not referenced by the cards: {sorted(own - used)}"


def test_each_text_has_enough_words_to_help_a_reader(doc) -> None:
    passage_id, _, _, _, cards = doc
    assert 25 <= len(cards["words"]) <= 70, f"{passage_id}: {len(cards['words'])} word cards (aim for 25 to 40 headwords plus inflected forms)"


def test_word_key_matches_the_browser_rule() -> None:
    assert word_key("“Hello,”") == "hello"
    assert word_key("there's") == "there's"
    assert word_key("nature.") == "nature"
    assert word_key("good—") == "good"
    assert word_key("—") == ""


def test_publish_cards_copies_only_cards_files(tmp_path) -> None:
    import cards_files

    src, dest = tmp_path / "src", tmp_path / "data"
    src.mkdir()
    (src / "a.cards.json").write_text("{}", encoding="utf-8")
    (src / "REVIEW.md").write_text("x", encoding="utf-8")
    (src / "places.raw.json").write_text("x", encoding="utf-8")
    (src / "images").mkdir()
    (src / "images" / "x.place-y-12345678.jpg").write_bytes(b"jpg")
    (src / "images" / "notes.txt").write_text("no", encoding="utf-8")
    assert cards_files.publish_cards(src, dest) == ["a.cards.json", "x.place-y-12345678.jpg"]
    assert sorted(p.name for p in dest.iterdir()) == ["a.cards.json", "x.place-y-12345678.jpg"]
    assert cards_files.publish_cards(tmp_path / "missing", dest) == []


def test_the_real_cards_publish_into_data(tmp_path) -> None:
    import cards_files

    copied = cards_files.publish_cards(CARDS, tmp_path)
    assert [n for n in copied if n.endswith(".cards.json")] == sorted(f"{i}.cards.json" for i in EXPECTED)
    assert len([n for n in copied if ".place-" in n]) == len(list((CARDS / "images").glob("*.*")))
