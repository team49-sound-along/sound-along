"""Publishing a translation as its own linked passage, with the links both ways and a sentence map for keeping the reader's place."""
import json

import pytest

import translate_flow as tf
from translate import Translated

SRC = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98"
PASSAGE = {"uuid": SRC, "title": "Park", "content": "<p>Hello there. Big park!</p>", "language": "en", "source": "generated",
           "settings": {"voice": "af_heart", "voiceEs": "ef_dora", "speed": 0.95, "mp3Kbps": 48}, "pronunciations": {"gaieties": "gayetees"}}
TRANSLATED = Translated(title="Parque", content_html="<p>Hola. Un parque grande. ¡Qué bien!</p>", sentence_map=[[0], [1, 2]], unprotected=[])


def test_the_translated_passage_has_its_own_stable_id_and_never_the_sources():
    a, b = tf.translated_id(SRC, "es"), tf.translated_id(SRC, "es")
    assert a == b != SRC and tf.translated_id(SRC, "en") != a and len(a) == 36


def test_invert_map_gives_the_source_sentence_for_every_target_sentence():
    assert tf.invert_map([[0], [1, 2]], 3) == [0, 1, 1]
    assert tf.invert_map([[0, 1], [2]], 3) == [0, 0, 1]
    with pytest.raises(ValueError, match="does not cover"):
        tf.invert_map([[0], [2]], 3)


def test_the_translated_job_input_is_a_spanish_passage_with_the_spanish_voice_and_no_english_pronunciations():
    job = tf.build_translated_passage(PASSAGE, "es", TRANSLATED)
    assert job["uuid"] == tf.translated_id(SRC, "es") and job["language"] == "es" and job["title"] == "Parque" and job["content"] == TRANSLATED.content_html
    assert job["settings"]["voiceEs"] == "ef_dora" and job["pronunciations"] == {} and job["source"] == "generated"
    assert "humanPassageId" not in job and "recording" not in job and not job.get("qualityCheck")


def test_translating_to_english_uses_the_english_voice_setting():
    es = {**PASSAGE, "language": "es", "uuid": "5e5f1d3c-7a2b-4c9e-8d1a-3b6f2c9e4a70"}
    job = tf.build_translated_passage(es, "en", TRANSLATED)
    assert job["language"] == "en" and job["settings"]["voice"] == "af_heart"


def test_links_are_written_into_both_documents_without_mutating_them():
    src, dst = {"id": SRC, "words": []}, {"id": "T", "words": []}
    new_src, new_dst = tf.link(src, dst, "es", "T", "en", TRANSLATED, 3)
    assert new_src["translations"] == {"es": {"id": "T", "sentenceMap": [[0], [1, 2]]}}
    assert new_dst["translationOf"] == {"id": SRC, "lang": "en", "sentenceMap": [0, 1, 1]} and new_dst["machineTranslated"] is True
    assert "translations" not in src and "translationOf" not in dst


def test_publish_runs_the_flow_for_the_new_id_then_links_every_source_variant_and_the_translation(tmp_path):
    for name in (SRC, "181b9f7b-6e16-57ce-bec2-a48c90d591d0"):  # the AI variant and its human variant
        (tmp_path / f"{name}.timing.json").write_text(json.dumps({"id": name, "words": []}))
    tid = tf.translated_id(SRC, "es")
    seen = {}

    def fake_run(job, data_dir):
        seen["job"] = job
        (data_dir / f"{job['uuid']}.timing.json").write_text(json.dumps({"id": job["uuid"], "words": [{"sentence": 0}, {"sentence": 1}, {"sentence": 2}]}))
        return {"id": job["uuid"]}

    out = tf.publish_translation(PASSAGE, tmp_path, "es", translated=TRANSLATED, run_fn=fake_run, source_ids=[SRC, "181b9f7b-6e16-57ce-bec2-a48c90d591d0"])
    assert out == tid and seen["job"]["language"] == "es"
    for name in (SRC, "181b9f7b-6e16-57ce-bec2-a48c90d591d0"):
        assert json.loads((tmp_path / f"{name}.timing.json").read_text())["translations"]["es"]["id"] == tid
    assert json.loads((tmp_path / f"{tid}.timing.json").read_text())["translationOf"]["id"] == SRC


def test_a_failure_in_the_translation_never_raises_to_the_caller(tmp_path):
    (tmp_path / f"{SRC}.timing.json").write_text(json.dumps({"id": SRC}))

    def boom(job, data_dir):
        raise RuntimeError("tts exploded")

    assert tf.publish_translation(PASSAGE, tmp_path, "es", translated=TRANSLATED, run_fn=boom, source_ids=[SRC], safe=True) is None
    assert "translations" not in json.loads((tmp_path / f"{SRC}.timing.json").read_text())  # no dangling link to a passage that does not exist


def test_the_other_language_is_chosen_from_the_passage_language():
    assert tf.other_language("en") == "es" and tf.other_language("es") == "en" and tf.other_language(None) == "es"


def test_langlinks_localiser_maps_names_to_the_other_languages_titles_and_drops_qualifiers():
    reply = {"query": {"normalized": [], "pages": {"1": {"title": "Great Britain", "langlinks": [{"lang": "es", "*": "Gran Bretaña"}]},
                                                    "2": {"title": "Georgia (U.S. state)", "langlinks": [{"lang": "es", "*": "Georgia (Estados Unidos)"}]},
                                                    "3": {"title": "Nowhere"}}}}
    got = tf.localize_with_wikipedia(["Great Britain", "Georgia (U.S. state)", "Nowhere"], "en", "es", http_get=lambda url, binary=False: reply)
    assert got == {"Great Britain": "Gran Bretaña", "Georgia (U.S. state)": "Georgia"}


def test_a_localiser_failure_gives_no_names_and_never_raises():
    def boom(url, binary=False):
        raise OSError("offline")

    assert tf.localize_with_wikipedia(["Great Britain"], "en", "es", http_get=boom) == {}


def test_publish_also_writes_translated_cards_and_their_pictures_when_a_translator_is_given(tmp_path):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (72).to_bytes(4, "big") * 2 + b"\x08\x06\x00\x00\x00" + b"p" * 30
    (tmp_path / f"{SRC}.timing.json").write_text(json.dumps({"id": SRC, "words": []}))
    (tmp_path / f"{SRC}.word-cookies-0a1b2c3d.png").write_bytes(png)
    (tmp_path / f"{SRC}.cards.json").write_text(json.dumps({"words": {"cookies": {"word": "cookies", "partOfSpeech": "noun", "definition": "", "spanish": [],
        "imageUrl": f"/data/{SRC}.word-cookies-0a1b2c3d.png", "imageAlt": "cookie", "imageCredit": "Picture: OpenMoji, CC BY-SA 4.0"}}, "places": {}}))

    def fake_run(job, data_dir):
        words = [{"text": t, "sentence": 0} for t in ["Me", "gustan", "las", "galletas."]]
        (data_dir / f"{job['uuid']}.timing.json").write_text(json.dumps({"id": job["uuid"], "words": words}))

    translated = Translated(title="Parque", content_html="<p>Me gustan las galletas.</p>", sentence_map=[[0]], unprotected=[])
    tid = tf.publish_translation(PASSAGE, tmp_path, "es", translated=translated, run_fn=fake_run, source_ids=[SRC],
                                 model=lambda xs: ["galletas" if x == "cookies" else "galleta" if x == "cookie" else x for x in xs])
    cards = json.loads((tmp_path / f"{tid}.cards.json").read_text())
    assert cards["words"]["galletas"]["translation"]["words"] == ["cookies"] and cards["machineTranslated"] is True
    assert (tmp_path / cards["words"]["galletas"]["imageUrl"].removeprefix("/data/")).read_bytes() == png


# ---- when an upload gets a translation -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("passage,expected", [
    ({"uuid": SRC, "source": "generated", "language": "en"}, True),
    ({"uuid": SRC, "source": "generated", "language": "es"}, True),
    ({"uuid": SRC, "source": "generated"}, True),
    ({"uuid": SRC, "source": "generated", "settings": {"translate": False}}, False),
    ({"uuid": SRC, "source": "generated", "noTranslate": True}, False),  # a translation is never translated again
    ({"uuid": SRC, "source": "sample", "language": "en"}, False),  # demo texts are translated by scripts/build_translations.py
    ({"uuid": SRC, "source": "generated", "language": "fr"}, False),
])
def test_which_passages_get_an_automatic_translation(passage, expected):
    assert tf.should_translate(passage) is expected


def test_the_translated_job_is_marked_so_it_is_never_translated_again():
    job = tf.build_translated_passage(PASSAGE, "es", TRANSLATED)
    assert job["noTranslate"] is True and tf.should_translate(job) is False


def test_localiser_follows_wikipedia_redirects_so_britain_finds_great_britain():
    reply = {"query": {"redirects": [{"from": "Britain", "to": "Great Britain"}],
                       "pages": {"1": {"title": "Great Britain", "langlinks": [{"lang": "es", "*": "Gran Bretaña"}]}}}}
    assert tf.localize_with_wikipedia(["Britain"], "en", "es", http_get=lambda url, binary=False: reply) == {"Britain": "Gran Bretaña"}


def test_localiser_keeps_the_original_when_the_article_title_is_much_longer_than_the_name():
    reply = {"query": {"pages": {"1": {"title": "China", "langlinks": [{"lang": "es", "*": "República Popular China"}]},
                                 "2": {"title": "United States", "langlinks": [{"lang": "es", "*": "Estados Unidos"}]}}}}
    assert tf.localize_with_wikipedia(["China", "United States"], "en", "es", http_get=lambda url, binary=False: reply) == {"United States": "Estados Unidos"}


def test_a_translated_part_stays_part_n_of_the_same_document():
    series = {"id": "5af24980-4d6d-41c1-87fa-4f21cb2d169d", "index": 2, "total": 3, "title": "T", "partIds": [f"2b781dab-4521-40d2-a9b6-ad5f2bb0ba9{i}" for i in range(3)]}
    assert tf.build_translated_passage({**PASSAGE, "series": series}, "es", TRANSLATED)["series"] == series
    assert "series" not in tf.build_translated_passage(PASSAGE, "es", TRANSLATED)


def test_the_operator_can_switch_automatic_translation_off(monkeypatch):
    monkeypatch.setenv("TRANSLATE_UPLOADS", "off")
    assert tf.should_translate({"uuid": SRC, "source": "generated", "language": "en"}) is False
    monkeypatch.setenv("TRANSLATE_UPLOADS", "on")
    assert tf.should_translate({"uuid": SRC, "source": "generated", "language": "en"}) is True


# ---- the passage stays out of the Library until its translation is in place ---------------------------------------------------------
def test_release_takes_the_held_marker_off_and_leaves_everything_else_alone(tmp_path):
    (tmp_path / f"{SRC}.timing.json").write_text(json.dumps({"id": SRC, "held": True, "title": "Park", "words": [1]}))
    (tmp_path / "other.timing.json").write_text(json.dumps({"id": "other", "title": "Unmarked"}))
    tf.release(tmp_path, [SRC, "other", "missing-id"])  # a missing file is not an error
    assert json.loads((tmp_path / f"{SRC}.timing.json").read_text()) == {"id": SRC, "title": "Park", "words": [1]}
    assert json.loads((tmp_path / "other.timing.json").read_text()) == {"id": "other", "title": "Unmarked"}


def test_a_passage_that_will_be_translated_is_written_held_and_one_that_will_not_is_not():
    import numpy as np
    from flow import Variant
    from run_local import _held_if_translating

    variant = Variant(id=SRC, audio=np.zeros(1, dtype="float32"), timing={"id": SRC})
    assert _held_if_translating({"source": "generated", "language": "en"}, variant).timing["held"] is True
    assert "held" not in _held_if_translating({"source": "generated", "language": "en", "settings": {"translate": False}}, variant).timing
    assert "held" not in _held_if_translating({"source": "sample", "language": "en"}, variant).timing
    assert "held" not in variant.timing  # the input is never changed


def test_a_passage_that_is_already_published_is_not_held_again_when_it_is_regenerated(tmp_path):
    import numpy as np
    from flow import Variant
    from run_local import _held_if_translating

    variant = Variant(id=SRC, audio=np.zeros(1, dtype="float32"), timing={"id": SRC})
    passage = {"source": "generated", "language": "en"}
    assert _held_if_translating(passage, variant, tmp_path).timing["held"] is True  # first publication
    (tmp_path / f"{SRC}.timing.json").write_text(json.dumps({"id": SRC}))  # published, listed
    assert "held" not in _held_if_translating(passage, variant, tmp_path).timing  # regeneration: stays listed
    (tmp_path / f"{SRC}.timing.json").write_text(json.dumps({"id": SRC, "held": True}))  # a run that never finished
    assert _held_if_translating(passage, variant, tmp_path).timing["held"] is True
