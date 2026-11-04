"""Joining the chunks of a long document into one passage."""
import numpy as np
import pytest

import stitch as st
from engine import SAMPLE_RATE

SR = SAMPLE_RATE


def words(texts, per_sentence=2, paragraph=0, step_ms=500):
    return [{"i": i, "text": t, "start_ms": i * step_ms, "end_ms": i * step_ms + 400, "sentence": i // per_sentence, "paragraph": paragraph,
             "aligned": True, "phraseEnd": False} for i, t in enumerate(texts)]


def tone(seconds, level=0.3):
    return (np.sin(np.linspace(0, 200 * seconds, int(SR * seconds))) * level).astype(np.float32)


def chunk(texts, seconds, lang="en", cid="c", extra=None, cards=None, paragraphs=1):
    w = words(texts)
    for k, word in enumerate(w):
        word["paragraph"] = k * paragraphs // len(w)
    timing = {"id": cid, "title": "Doc (internal)", "engine": "kokoro", "voice": "af_heart", "duration_ms": round(seconds * 1000),
              "metrics": {"characters": 50, "words": len(w), "audioSeconds": seconds, "generateSeconds": 2.0, "realTimeFactor": 0.1, "unalignedWords": 1,
                          "pollyNeuralUsd": 0.01, "pollyStandardUsd": 0.002, "estimatedLambdaUsd": 0.001, "estimateBasis": "x"},
              "vocab": {}, "words": w, "language": lang, "generatedWith": {"settings": {"voice": "af_heart"}, "hash": "chunk-hash"}, **(extra or {})}
    return st.Chunk(timing, tone(seconds), cards)


def two_chunks():
    return [chunk(["a", "b", "c", "d"], 3.0, cid="c1"), chunk(["e", "f", "g", "h", "i", "j"], 4.0, cid="c2")]


def test_the_result_is_one_ordinary_passage_with_the_documents_own_id_and_title():
    out = st.stitch(two_chunks(), "FINAL", "The Whole Story", fingerprint="whole-hash")
    t = out.timing
    assert t["id"] == "FINAL" and t["title"] == "The Whole Story" and "series" not in t and t["generatedWith"]["hash"] == "whole-hash"
    assert t["generatedWith"]["settings"] == {"voice": "af_heart"} and t["language"] == "en" and t["voice"] == "af_heart"
    assert "Part" not in t["title"]


def test_word_numbers_sentences_and_paragraphs_continue_across_the_join_and_times_only_go_up():
    t = st.stitch(two_chunks(), "F", "T").timing
    w = t["words"]
    assert [x["i"] for x in w] == list(range(10)) and [x["text"] for x in w] == list("abcdefghij")
    assert [x["sentence"] for x in w] == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]  # chunk 1 has sentences 0 and 1, chunk 2 continues at 2
    assert [x["paragraph"] for x in w] == [0] * 4 + [1] * 6
    assert all(w[k]["start_ms"] <= w[k + 1]["start_ms"] and w[k]["start_ms"] < w[k]["end_ms"] for k in range(len(w) - 1))


def test_the_second_chunks_times_are_shifted_by_the_first_chunks_audio_plus_one_paragraph_pause():
    out = st.stitch(two_chunks(), "F", "T")
    shift = round((3.0 + st.PARAGRAPH_GAP_S) * 1000)
    first_of_second = out.timing["words"][4]
    assert first_of_second["start_ms"] == 0 + shift and first_of_second["end_ms"] == 400 + shift
    assert len(out.audio) >= int((3.0 + st.PARAGRAPH_GAP_S + 4.0) * SR) - 2
    assert out.timing["duration_ms"] == round(len(out.audio) / SR * 1000)


def test_a_word_in_the_second_chunk_is_where_the_audio_says_it_is():
    # the first chunk is a quiet tone, the second a loud one: the second chunk's first word must start where the loud audio starts
    quiet, loud = chunk(["a", "b"], 2.0, cid="q"), chunk(["c", "d"], 2.0, cid="l")
    out = st.stitch([st.Chunk(quiet.timing, tone(2.0, 0.05)), st.Chunk(loud.timing, tone(2.0, 0.4))], "F", "T")
    start = out.timing["words"][2]["start_ms"] / 1000
    window = out.audio[int(start * SR): int((start + 0.5) * SR)]
    before = out.audio[int((start - 0.4) * SR): int((start - 0.1) * SR)]
    assert np.abs(window).max() > 0.05 and np.abs(before).max() < 0.01  # silence (the pause) just before the second chunk's first word


def test_loudness_is_matched_across_chunks_and_normalised_once():
    out = st.stitch([st.Chunk(chunk(["a"], 2.0).timing, tone(2.0, 0.1)), st.Chunk(chunk(["b"], 2.0).timing, tone(2.0, 0.2))], "F", "T")
    a, b = out.audio[: 2 * SR], out.audio[-2 * SR:]
    ratio = np.sqrt((b ** 2).mean()) / np.sqrt((a ** 2).mean())
    assert 0.9 < ratio < 1.5  # a 2x difference (6 dB) is pulled to within the 3 dB limit around the median
    assert abs(float(np.abs(out.audio).max()) - 10 ** (-1 / 20)) < 0.01  # one peak level for the whole passage


def test_metrics_are_summed_and_the_real_time_factor_is_recomputed():
    m = st.stitch(two_chunks(), "F", "T").timing["metrics"]
    assert m["words"] == 10 and m["characters"] == 100 and m["audioSeconds"] == 7.0 and m["generateSeconds"] == 4.0 and m["unalignedWords"] == 2
    assert m["realTimeFactor"] == round(4.0 / 7.0, 3) and m["pollyNeuralUsd"] == 0.02 and m["estimateBasis"] == "x"


def test_review_notes_are_combined_and_the_inputs_are_never_changed():
    review = lambda s: {"review": {"source": "asr-check", "suspects": [s]}}
    chunks = [chunk(["a", "b"], 1.0, extra=review({"expected": "Mara", "heard": "Mira"})), chunk(["c", "d"], 1.0, extra=review({"expected": "her", "heard": "hair"}))]
    snapshot = [(c.timing["words"][0]["start_ms"], c.timing["words"][0]["i"], len(c.audio)) for c in chunks]
    out = st.stitch(chunks, "F", "T")
    assert [s["expected"] for s in out.timing["review"]["suspects"]] == ["Mara", "her"]
    assert snapshot == [(c.timing["words"][0]["start_ms"], c.timing["words"][0]["i"], len(c.audio)) for c in chunks] and chunks[1].timing["words"][0]["i"] == 0


def test_an_unknown_timing_field_or_a_human_variant_or_mixed_voices_is_an_error_not_silently_dropped():
    with pytest.raises(ValueError, match="does not know the timing field"):
        st.stitch([chunk(["a"], 1.0, extra={"brandNewField": 1})], "F", "T")
    with pytest.raises(ValueError, match="human recording"):
        st.stitch([chunk(["a"], 1.0, extra={"pairId": "x"})], "F", "T")
    other = chunk(["b"], 1.0)
    other.timing["voice"] = "af_bella"
    with pytest.raises(ValueError, match="same language and voice"):
        st.stitch([chunk(["a"], 1.0), other], "F", "T")
    with pytest.raises(ValueError, match="nothing to stitch"):
        st.stitch([], "F", "T")


def card(word, url=None):
    return {"word": word, **({"imageUrl": url} if url else {})}


def test_cards_are_combined_first_card_wins_and_picture_links_point_at_the_new_passage():
    a = {"words": {"park": card("park", "/data/c1.word-park-1.png")}, "places": {"Atlanta": {"name": "Atlanta"}}, "reviewed": False}
    b = {"words": {"park": card("park!", "/data/c2.word-park-2.png"), "tree": card("tree")}, "places": {"Georgia": {"name": "Georgia"}}, "figures": [{"id": 1}]}
    merged = st.merge_cards([a, None, b])
    assert set(merged["words"]) == {"park", "tree"} and merged["words"]["park"]["word"] == "park" and set(merged["places"]) == {"Atlanta", "Georgia"}
    assert merged["figures"] == [{"id": 1}] and merged["reviewed"] is False and st.merge_cards([None, None]) is None
    moved = st.retarget_ids(merged, ["c1", "c2"], "FINAL")
    assert moved["words"]["park"]["imageUrl"] == "/data/FINAL.word-park-1.png" and "c1." not in str(moved)


def translated(texts, seconds, cid, source_id, sentence_map_to_source):
    c = chunk(texts, seconds, lang="es", cid=cid, extra={"machineTranslated": True, "translationOf": {"id": source_id, "lang": "en", "sentenceMap": sentence_map_to_source}})
    return c


def test_the_sentence_maps_of_every_chunk_are_shifted_and_joined_in_both_directions():
    en = [chunk(["a", "b", "c", "d"], 3.0, cid="e1", extra={"translations": {"es": {"id": "s1", "sentenceMap": [[0], [1, 2]]}}}),  # 2 EN sentences -> 3 ES
          chunk(["e", "f", "g", "h"], 3.0, cid="e2", extra={"translations": {"es": {"id": "s2", "sentenceMap": [[0], [1]]}}})]  # 2 EN -> 2 ES
    es = [translated(["w", "x", "y", "z", "u", "v"], 3.0, "s1", "e1", [0, 1, 1]), translated(["m", "n", "o", "p"], 3.0, "s2", "e2", [0, 1])]
    e, s = st.stitch(en, "EN", "T"), st.stitch(es, "ES", "T")
    src, dst = st.link_translation(e, s, en, es, "es", "en", "EN", "ES")
    assert src["translations"] == {"es": {"id": "ES", "sentenceMap": [[0], [1, 2], [3], [4]]}}
    assert dst["translationOf"] == {"id": "EN", "lang": "en", "sentenceMap": [0, 1, 1, 2, 3]} and dst["machineTranslated"] is True
    assert "translations" not in dst and "translationOf" not in src


def test_linking_refuses_chunks_that_do_not_line_up():
    en = [chunk(["a", "b"], 1.0, extra={"translations": {"es": {"id": "s", "sentenceMap": [[0]]}}})]
    es = [translated(["w", "x"], 1.0, "s", "e", [0])]
    with pytest.raises(ValueError, match="every chunk needs its translation"):
        st.link_translation(st.stitch(en, "EN", "T"), st.stitch(es, "ES", "T"), en, [], "es", "en", "EN", "ES")
    bad = [translated(["w", "x", "y", "z"], 1.0, "s", "e", [0])]  # two sentences but a map for one
    with pytest.raises(ValueError, match="do not match"):
        st.link_translation(st.stitch(en, "EN", "T"), st.stitch(bad, "ES", "T"), en, bad, "es", "en", "EN", "ES")


def test_the_pause_matches_the_narrations_paragraph_gap():
    import pipeline

    assert st.PARAGRAPH_GAP_S == pipeline.PARAGRAPH_GAP_S
