"""Definition cards for the harder words of an uploaded passage (offline dictionary, see scripts/build_word_definitions.py)."""
import word_definitions as wd

TABLE = {
    "enormous": {"a": [["extremely large", "an enormous elephant", "ɪnˈɔːməs"]]},
    "elephant": {"n": [["a very large animal with a trunk", "", ""]]},
    "stomp": {"v": [["to walk with heavy steps", "", ""]]},
    "slowly": {"r": [["at a slow pace", "", ""]]},
    "walk": {"v": [["to move on foot", "", ""]]},
    "bank": {"n": [["land beside a river", "", ""]], "v": [["to tilt in turning", "", ""]]},
    "hive": {"n": [["a teeming multitude", "", ""], ["a nest of bees with honey and wax", "", ""]]},
}
COMMON = {"walk"}


def toks(text):
    # (surface, lemma, pos) as spaCy would give them
    return [(w.lower(), {"elephants": "elephant", "stomped": "stomp"}.get(w.lower(), w.lower()), pos) for w, pos in
            [("The", "DET"), ("enormous", "ADJ"), ("elephants", "NOUN"), ("stomped", "VERB"), ("slowly", "ADV"), ("Anna", "PROPN"), ("walk", "VERB"), ("zzz", "NOUN")]]


def cards(**kw):
    return wd.definition_cards("x " * 10, table=TABLE, common=COMMON, tokens=toks, **kw)


def test_hard_content_words_get_a_definition_card_and_names_common_words_and_unknown_words_do_not():
    got = cards(minimum=10)
    assert set(got) == {"enormous", "elephants", "stomped", "slowly"}
    c = got["enormous"]
    assert c["definition"] == "extremely large" and c["partOfSpeech"] == "adjective" and c["example"] == "an enormous elephant" and c["ipa"] == "ɪnˈɔːməs"
    assert got["elephants"]["word"] == "elephants" and got["elephants"]["definition"].startswith("a very large animal")
    assert got["stomped"]["partOfSpeech"] == "verb" and got["slowly"]["partOfSpeech"] == "adverb"


def test_the_sense_that_fits_the_passage_wins_over_the_most_frequent_one():
    def t(text):
        return [("bees", "bee", "NOUN"), ("honey", "honey", "NOUN"), ("hive", "hive", "NOUN")]
    got = wd.definition_cards("x", table=TABLE, common=set(), tokens=t, minimum=5)
    assert got["hive"]["definition"] == "a nest of bees with honey and wax"
    lone = wd.definition_cards("x", table=TABLE, common=set(), tokens=lambda _: [("hive", "hive", "NOUN")], minimum=5)
    assert lone["hive"]["definition"] == "a teeming multitude"


def test_the_number_of_cards_follows_the_length_of_the_passage_with_a_floor_and_a_ceiling():
    assert len(cards(minimum=2, maximum=2)) == 2
    assert wd.card_budget(40, per_hundred=5, minimum=8, maximum=120) == 8
    assert wd.card_budget(1000, per_hundred=5, minimum=8, maximum=120) == 50
    assert wd.card_budget(12000, per_hundred=5, minimum=8, maximum=120) == 120


def test_an_existing_reviewed_card_keeps_its_text_and_only_gains_what_it_lacks():
    existing = {"enormous": {"word": "enormous", "definition": "teacher wrote this", "ipa": None, "example": None, "spanish": ["enorme"], "partOfSpeech": "adjective"}}
    got = cards(minimum=10, existing=existing)
    assert got["enormous"]["definition"] == "teacher wrote this" and got["enormous"]["spanish"] == ["enorme"] and got["enormous"]["ipa"] == "ɪnˈɔːməs"


def test_a_noun_that_is_also_a_verb_gets_the_sense_for_its_part_of_speech():
    def t(text):
        return [("banks", "bank", "VERB"), ("river", "river", "NOUN")]
    got = wd.definition_cards("x", table=TABLE, common=set(), tokens=t, minimum=5)
    assert got["banks"]["definition"] == "to tilt in turning" and got["banks"]["partOfSpeech"] == "verb"


def test_a_missing_or_broken_dictionary_gives_no_cards_and_never_raises():
    def boom(text):
        raise RuntimeError("no model")
    assert wd.definition_cards("x", table=TABLE, common=set(), tokens=boom) == {}
    assert wd.definition_cards("x", table={}, common=set(), tokens=toks) == {}


def test_long_glosses_are_cut_at_a_clause_not_mid_word():
    assert wd.short_gloss("a very long explanation that goes on; and then some other sense", 200) == "a very long explanation that goes on"
    g = wd.short_gloss("word " * 60, 60)
    assert len(g) <= 61 and g.endswith("…")
