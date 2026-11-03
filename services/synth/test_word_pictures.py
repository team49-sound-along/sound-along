"""Word pictures: any concrete noun in any passage (cookies, tea, trees) can get a small picture. Offline: the photos ship with the generator."""
import json

import pytest

import word_pictures as wp

PID = "0e8b1b1e-1111-4222-8333-444455556666"
JPG = b"\xff\xd8\xff\xe0" + b"j" * 60
CREDIT = "Photo: A. Author, CC BY-SA 4.0, via Wikimedia Commons"


@pytest.fixture()
def pack(tmp_path):
    table = {k: {"file": f"{k}.jpg", "name": k, "credit": CREDIT} for k in ("cookie", "tea", "tree")}
    folder = tmp_path / "word_photos"
    folder.mkdir()
    for k in table:
        (folder / f"{k}.jpg").write_bytes(JPG)
    return table, folder


def nouns_of(text):
    """Stand-in for spaCy: every word is a noun whose lemma drops a plural s."""
    return [(w, w[:-1] if w.endswith("s") and len(w) > 3 else w) for w in __import__("re").findall(r"[A-Za-z]+", text.lower())]


def test_a_plural_noun_gets_the_picture_of_its_singular_under_the_word_as_written(pack):
    table, folder = pack
    cards, images = wp.word_picture_cards(PID, "They bought cookies and tea near the trees.", nouns=nouns_of, table=table, photo_dir=folder)
    assert sorted(cards) == ["cookies", "tea", "trees"]
    card = cards["cookies"]
    assert card["word"] == "cookies" and card["partOfSpeech"] == "noun" and card["definition"] == "" and card["spanish"] == []
    name = card["imageUrl"].removeprefix("/data/")
    assert wp.NAME_PATTERN.fullmatch(name) and name.startswith(f"{PID}.word-cookies-") and images[name] == JPG
    assert card["imageAlt"] == "photo of cookie" and name.endswith(".jpg")
    assert card["imageCredit"] == CREDIT


def test_words_without_a_picture_and_words_that_are_not_nouns_are_left_alone(pack):
    table, folder = pack
    cards, _ = wp.word_picture_cards(PID, "They bought cookies quickly.", nouns=lambda t: [("cookies", "cookie")], table=table, photo_dir=folder)
    assert list(cards) == ["cookies"]
    assert wp.word_picture_cards(PID, "Nothing here.", nouns=lambda t: [("nothing", "nothing")], table=table, photo_dir=folder) == ({}, {})
    assert wp.word_picture_cards(PID, "x", nouns=lambda t: [], table=table, photo_dir=folder) == ({}, {})


def test_each_word_appears_once_in_order_and_the_number_of_cards_is_capped(pack):
    table, folder = pack
    cards, _ = wp.word_picture_cards(PID, "tea tea cookie tea tree", nouns=nouns_of, table=table, photo_dir=folder, limit=2)
    assert list(cards) == ["tea", "cookie"]


def test_existing_reviewed_cards_keep_their_definitions_and_only_gain_the_picture(pack):
    table, folder = pack
    existing = {"tea": {"word": "tea", "syllables": None, "ipa": None, "partOfSpeech": "noun", "definition": "A hot drink made from leaves.", "example": None, "spanish": ["té"]}}
    cards, images = wp.word_picture_cards(PID, "tea and cookies", nouns=nouns_of, table=table, photo_dir=folder, existing=existing)
    assert cards["tea"]["definition"] == "A hot drink made from leaves." and cards["tea"]["spanish"] == ["té"] and cards["tea"]["imageUrl"]
    assert cards["cookies"]["definition"] == "" and len(images) == 2


def test_a_missing_or_corrupt_icon_file_means_no_picture_never_a_crash(pack, tmp_path):
    table, folder = pack
    (folder / "cookie.jpg").write_bytes(b"not an image")
    (folder / "tea.jpg").unlink()
    cards, images = wp.word_picture_cards(PID, "cookie tea tree", nouns=nouns_of, table=table, photo_dir=folder)
    assert list(cards) == ["tree"] and len(images) == 1


def test_the_real_pack_has_free_licensed_photos_that_exist_and_are_small():
    table = wp.load_table()
    assert len(table) > 100 and all(set(v) >= {"file", "name", "credit"} for v in table.values())
    folder = wp.PHOTO_DIR
    assert all((folder / v["file"]).read_bytes()[:3] == b"\xff\xd8\xff" for v in table.values())
    assert max(p.stat().st_size for p in folder.glob("*.jpg")) <= 70_000
    assert all(v["credit"].startswith(("Photo: ", "Image: ")) and "via Wikimedia Commons" in v["credit"] for v in table.values())
    assert not any(" NC" in v["credit"].upper() or "NON-COMMERCIAL" in v["credit"].upper() for v in table.values())


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
    assert cards["cookies"]["imageAlt"].startswith("photo of ")
