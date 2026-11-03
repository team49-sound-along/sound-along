"""Word pictures: any concrete noun in any passage (cookies, tea, trees) can get a small picture. Offline: the icons ship with the generator."""
import json

import pytest

import word_pictures as wp

PID = "0e8b1b1e-1111-4222-8333-444455556666"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (72).to_bytes(4, "big") * 2 + b"\x08\x06\x00\x00\x00" + b"p" * 40


@pytest.fixture()
def pack(tmp_path):
    table = {"cookie": {"hex": "1F36A", "name": "cookie"}, "tea": {"hex": "2615", "name": "hot beverage"}, "tree": {"hex": "1F333", "name": "deciduous tree"}}
    folder = tmp_path / "emoji"
    folder.mkdir()
    for h in ("1F36A", "2615", "1F333"):
        (folder / f"{h}.png").write_bytes(PNG)
    return table, folder


def nouns_of(text):
    """Stand-in for spaCy: every word is a noun whose lemma drops a plural s."""
    return [(w, w[:-1] if w.endswith("s") and len(w) > 3 else w) for w in __import__("re").findall(r"[A-Za-z]+", text.lower())]


def test_a_plural_noun_gets_the_picture_of_its_singular_under_the_word_as_written(pack):
    table, folder = pack
    cards, images = wp.word_picture_cards(PID, "They bought cookies and tea near the trees.", nouns=nouns_of, table=table, emoji_dir=folder)
    assert sorted(cards) == ["cookies", "tea", "trees"]
    card = cards["cookies"]
    assert card["word"] == "cookies" and card["partOfSpeech"] == "noun" and card["definition"] == "" and card["spanish"] == []
    name = card["imageUrl"].removeprefix("/data/")
    assert wp.NAME_PATTERN.fullmatch(name) and name.startswith(f"{PID}.word-cookies-") and images[name] == PNG
    assert card["imageAlt"] == "cookie" and (card["imageWidth"], card["imageHeight"]) == (72, 72)
    assert card["imageCredit"] == "Picture: OpenMoji, CC BY-SA 4.0"


def test_words_without_a_picture_and_words_that_are_not_nouns_are_left_alone(pack):
    table, folder = pack
    cards, _ = wp.word_picture_cards(PID, "They bought cookies quickly.", nouns=lambda t: [("cookies", "cookie")], table=table, emoji_dir=folder)
    assert list(cards) == ["cookies"]
    assert wp.word_picture_cards(PID, "Nothing here.", nouns=lambda t: [("nothing", "nothing")], table=table, emoji_dir=folder) == ({}, {})
    assert wp.word_picture_cards(PID, "x", nouns=lambda t: [], table=table, emoji_dir=folder) == ({}, {})


def test_each_word_appears_once_in_order_and_the_number_of_cards_is_capped(pack):
    table, folder = pack
    cards, _ = wp.word_picture_cards(PID, "tea tea cookie tea tree", nouns=nouns_of, table=table, emoji_dir=folder, limit=2)
    assert list(cards) == ["tea", "cookie"]


def test_existing_reviewed_cards_keep_their_definitions_and_only_gain_the_picture(pack):
    table, folder = pack
    existing = {"tea": {"word": "tea", "syllables": None, "ipa": None, "partOfSpeech": "noun", "definition": "A hot drink made from leaves.", "example": None, "spanish": ["té"]}}
    cards, images = wp.word_picture_cards(PID, "tea and cookies", nouns=nouns_of, table=table, emoji_dir=folder, existing=existing)
    assert cards["tea"]["definition"] == "A hot drink made from leaves." and cards["tea"]["spanish"] == ["té"] and cards["tea"]["imageUrl"]
    assert cards["cookies"]["definition"] == "" and len(images) == 2


def test_a_missing_or_corrupt_icon_file_means_no_picture_never_a_crash(pack, tmp_path):
    table, folder = pack
    (folder / "1F36A.png").write_bytes(b"not an image")
    (folder / "2615.png").unlink()
    cards, images = wp.word_picture_cards(PID, "cookie tea tree", nouns=nouns_of, table=table, emoji_dir=folder)
    assert list(cards) == ["tree"] and len(images) == 1


def test_the_real_pack_maps_cookies_and_the_icons_exist_and_are_small():
    table = wp.load_table()
    assert table["cookie"]["hex"] == "1F36A" and len(table) > 500
    folder = wp.EMOJI_DIR
    assert (folder / "1F36A.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert max(p.stat().st_size for p in folder.glob("*.png")) < 20_000
    assert all((folder / f"{v['hex']}.png").exists() for v in table.values())


def test_the_nouns_finder_works_with_the_real_spacy_model_when_it_is_installed():
    spacy = pytest.importorskip("spacy")
    try:
        spacy.load("en_core_web_sm")
    except OSError:
        pytest.skip("model not installed")
    pairs = wp.spacy_nouns("The children ate cookies near the old trees and drank tea in London.")
    surfaces = {s for s, _ in pairs}
    assert {"cookies", "trees", "tea"} <= surfaces and "london" not in surfaces
    cards, _ = wp.word_picture_cards(PID, "The children ate cookies near the old trees and drank tea in London.")
    assert {"cookies", "trees", "tea"} <= set(cards) and "london" not in cards  # whatever lemma spaCy picks, the written word finds its picture
    assert cards["cookies"]["imageAlt"] == "cookie"
