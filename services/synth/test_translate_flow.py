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
