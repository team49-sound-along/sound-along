"""Cards for a translated passage: places keep their pictures, words are keyed by the Spanish word that is really in the text."""
import pytest

import translate_cards as tc

SRC = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98"
NEW = "7a1b2c3d-1111-5222-8333-444455556666"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (72).to_bytes(4, "big") * 2 + b"\x08\x06\x00\x00\x00" + b"p" * 30
JPEG = b"\xff\xd8\xff\xe0" + b"j" * 60

SOURCE = {
    "words": {
        "relax": {"word": "relax", "syllables": "re·lax", "ipa": None, "partOfSpeech": "verb", "definition": "To rest and feel calm.", "example": "A city park is a fun place to relax.", "spanish": ["relajarse"]},
        "cookies": {"word": "cookies", "syllables": None, "ipa": None, "partOfSpeech": "noun", "definition": "", "example": None, "spanish": [],
                    "imageUrl": f"/data/{SRC}.word-cookies-0a1b2c3d.png", "imageAlt": "cookie", "imageCredit": "Picture: OpenMoji, CC BY-SA 4.0", "imageWidth": 72, "imageHeight": 72},
        "nature": {"word": "nature", "syllables": "na·ture", "ipa": None, "partOfSpeech": "noun", "definition": "Everything not made by people.", "example": None, "spanish": ["naturaleza", "mundo natural"]},
    },
    "places": {
        "Piedmont Park": {"name": "Piedmont Park", "summary": "A big public park.", "attribution": "Wikipedia, CC BY-SA", "imageUrl": f"/data/{SRC}.place-piedmont-park-e96cde8f.jpg",
                          "imageAlt": "A calm lake.", "imageCredit": "Photo: Frank, CC BY-SA 4.0, via Wikimedia Commons", "imageWidth": 500, "imageHeight": 625},
        "Great Britain": {"name": "Great Britain", "summary": "The big island.", "attribution": "Wikipedia, CC BY-SA", "imageUrl": None, "imageAlt": None, "imageCredit": None, "imageWidth": None, "imageHeight": None},
        "Atlanta": {"name": "Atlanta", "summary": "A city.", "attribution": "Wikipedia, CC BY-SA", "imageUrl": None, "imageAlt": None, "imageCredit": None, "imageWidth": None, "imageHeight": None},
    },
}
WORDS = {"cookies": "galletas", "To rest and feel calm.": "Descansar y sentirse tranquilo.", "Everything not made by people.": "Todo lo que no hacen las personas.",
         "A big public park.": "Un gran parque público.", "The big island.": "La gran isla.", "A calm lake.": "Un lago tranquilo.", "cookie": "galleta"}


def fake(texts):
    return [WORDS.get(t, "ES " + t) for t in texts]


def files():
    return {f"{SRC}.word-cookies-0a1b2c3d.png": PNG, f"{SRC}.place-piedmont-park-e96cde8f.jpg": JPEG}


TEXT = ["Quiero", "relajarme", "y", "relajarse", "en", "Piedmont", "Park", "con", "galletas", "y", "la", "naturaleza", "en", "Gran", "Bretaña."]


def run(**kw):
    return tc.translate_cards(SOURCE, TEXT, fake, SRC, NEW, files(), "es", localized={"Great Britain": "Gran Bretaña"}, **kw)


def test_word_key_matches_the_browser_rule():
    assert tc.word_key("“Hola,”") == "hola" and tc.word_key("Bretaña.") == "bretaña" and tc.word_key("—") == ""


def test_a_reviewed_word_is_keyed_by_the_spanish_word_that_is_really_in_the_text_and_shows_the_english_headword():
    doc, _ = run()
    card = doc["words"]["relajarse"]
    assert card["word"] == "relajarse" and card["partOfSpeech"] == "verb" and card["definition"] == "Descansar y sentirse tranquilo."
    assert card["translation"] == {"lang": "en", "words": ["relax"]} and card["example"] is None and card["spanish"] == []
    assert "relajarme" not in doc["words"]  # only a ReadWorks translation or a verified machine translation becomes a card


def test_the_first_spanish_term_that_appears_in_the_text_wins_for_a_word_with_several_translations():
    doc, _ = run()
    assert "naturaleza" in doc["words"] and "mundo" not in doc["words"] and doc["words"]["naturaleza"]["translation"]["words"] == ["nature"]


def test_a_picture_word_is_translated_and_kept_only_if_the_translation_appears_in_the_text_and_its_picture_is_copied_under_the_new_id():
    doc, images = run()
    card = doc["words"]["galletas"]
    assert card["translation"]["words"] == ["cookies"] and card["imageAlt"] == "galleta" and card["imageCredit"] == "Imagen: OpenMoji, CC BY-SA 4.0" and card["definition"] == ""
    name = card["imageUrl"].removeprefix("/data/")
    assert name.startswith(f"{NEW}.word-galletas-") and name.endswith(".png") and images[name] == PNG


def test_a_word_whose_translation_is_not_in_the_text_gets_no_card():
    doc, _ = tc.translate_cards(SOURCE, ["Hola", "mundo."], fake, SRC, NEW, files(), "es")
    assert doc["words"] == {}


def test_places_use_the_localised_name_only_when_it_appears_translate_the_summary_and_keep_the_picture():
    doc, images = run()
    assert sorted(doc["places"]) == ["Gran Bretaña", "Piedmont Park"]  # Atlanta is not in this text
    gb, park = doc["places"]["Gran Bretaña"], doc["places"]["Piedmont Park"]
    assert gb["name"] == "Gran Bretaña" and gb["summary"] == "La gran isla." and gb["imageUrl"] is None
    assert park["summary"] == "Un gran parque público." and park["imageAlt"] == "Un lago tranquilo."
    assert park["imageCredit"] == "Foto: Frank, CC BY-SA 4.0, vía Wikimedia Commons"
    assert park["attribution"] == "Wikipedia, CC BY-SA (traducción automática)"
    name = park["imageUrl"].removeprefix("/data/")
    assert name.startswith(f"{NEW}.place-piedmont-park-") and images[name] == JPEG


def test_the_document_is_marked_machine_translated_and_unreviewed():
    doc, _ = run()
    assert doc["reviewed"] is False and doc["machineTranslated"] is True and doc["source"] == "translated"


def test_every_text_field_respects_the_card_limits():
    long = {**SOURCE, "words": {"relax": {**SOURCE["words"]["relax"], "definition": "x" * 300}}}
    doc, _ = tc.translate_cards(long, TEXT, lambda t: ["Una frase larga. " + "palabra " * 60] * len(t), SRC, NEW, files(), "es")
    assert all(len(c["definition"]) <= 140 for c in doc["words"].values())
    assert all(len(p["summary"]) <= 160 for p in doc["places"].values())


def test_a_missing_picture_file_means_no_picture_never_a_crash():
    doc, images = tc.translate_cards(SOURCE, TEXT, fake, SRC, NEW, {}, "es", localized={})
    assert doc["words"]["galletas"]["imageUrl"] is None and images == {}


def test_translating_to_english_uses_english_credits_and_the_spanish_headword():
    doc, _ = tc.translate_cards({"words": {"galletas": {**SOURCE["words"]["cookies"], "word": "galletas", "spanish": ["cookies"]}}, "places": {}},
                                ["I", "like", "cookies."], lambda t: ["cookies" if x == "galletas" else x for x in t], SRC, NEW, {}, "en")
    assert doc["words"]["cookies"]["translation"] == {"lang": "es", "words": ["galletas"]}
