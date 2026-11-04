import spanish_cards as sc

COMMON = {"casa", "tiene"}
TR = {"elefante": "elephant", "enorme": "huge.", "caminaba": "Walked"}


def fake(words):
    return [TR.get(w, w) for w in words]


def cards(text, **kw):
    return sc.spanish_cards(text, translate=fake, common=COMMON, minimum=10, **kw)


def test_hard_words_get_an_english_translation_card_and_names_and_common_words_do_not():
    got = cards("El elefante enorme caminaba. Ana tiene una casa grande. Vimos a Pedro.")
    assert set(got) >= {"elefante", "enorme", "caminaba"}
    assert "ana" not in got and "pedro" not in got and "casa" not in got and "tiene" not in got
    c = got["elefante"]
    assert c["translation"] == {"lang": "en", "words": ["elephant"]} and c["definition"] == "" and c["machineTranslated"] is True


def test_the_translation_is_tidied_to_a_plain_lower_case_word():
    got = cards("El elefante enorme caminaba.")
    assert got["enorme"]["translation"]["words"] == ["huge"] and got["caminaba"]["translation"]["words"] == ["walked"]


def test_a_word_that_translates_to_itself_is_skipped_because_it_teaches_nothing():
    assert "radio" not in sc.spanish_cards("La radio suena.", translate=lambda ws: ws, common=set(), minimum=10)


def test_a_broken_translator_gives_no_cards_and_never_raises():
    def boom(ws):
        raise RuntimeError("no model")
    assert sc.spanish_cards("El elefante enorme.", translate=boom, common=set()) == {}


def test_the_number_of_cards_is_capped_by_the_passage_length():
    text = " ".join(f"palabra{chr(97 + i)}{chr(97 + j)}" for i in range(10) for j in range(10))
    assert len(sc.spanish_cards(text, translate=lambda ws: [w + "x" for w in ws], common=set(), minimum=4, maximum=4)) == 4
