import word_cards as wc


def pics(pid, text, existing=None):
    return {"cookies": {"word": "cookies", "definition": "", "imageUrl": "/data/x.jpg"}}, {"x.jpg": b"1"}


def defs(text, existing=None):
    base = (existing or {}).get("cookies", {})
    return {"cookies": {**base, "definition": "sweet baked treats"}, "tunnel": {"word": "tunnel", "definition": "a passage"}}


def test_a_word_with_a_picture_and_a_definition_is_one_card_with_both():
    cards, images = wc.word_cards("p", "t", pictures=pics, definitions=defs)
    assert cards["cookies"]["imageUrl"] == "/data/x.jpg" and cards["cookies"]["definition"] == "sweet baked treats" and "tunnel" in cards and images == {"x.jpg": b"1"}


def test_each_part_fails_alone():
    def boom(*a, **k):
        raise RuntimeError("x")
    assert set(wc.word_cards("p", "t", pictures=boom, definitions=defs)[0]) == {"cookies", "tunnel"}
    cards, images = wc.word_cards("p", "t", pictures=pics, definitions=boom)
    assert set(cards) == {"cookies"} and images
