"""Phrase breaks: `phraseEnd` on each timing word. Same rule as web/src/phrases.js (the browser's fallback), so the two never drift.

The cases below are copied from web/src/phrases.test.js; test_python_flags_give_the_same_lines_as_the_browser_rule checks the rule
against the real browser code on the real passages.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from phrases import phrase_ends

ROOT = Path(__file__).resolve().parents[2]


def mk(text, sentence=0, paragraph=0, i=0):
    return {"i": i, "text": text, "sentence": sentence, "paragraph": paragraph}


def make(sentences):
    words, i = [], 0
    for sentence, s in enumerate(sentences):
        for text in s.split(" "):
            words.append(mk(text, sentence, 0, i))
            i += 1
    return words


def lines(words):
    """Group words the way the reader does when flags are present: break after a flagged word or at a sentence end."""
    flagged = phrase_ends(words)
    out, current = [], []
    for index, w in enumerate(flagged):
        current.append(w["text"])
        nxt = flagged[index + 1] if index + 1 < len(flagged) else None
        if nxt is None or nxt["sentence"] != w["sentence"] or w["phraseEnd"]:
            out.append(" ".join(current))
            current = []
    return out


def test_breaks_after_a_comma_once_the_line_has_three_or_more_words():
    words = make(["A city park is a fun place to relax, play, and enjoy nature."])
    assert lines(words) == ["A city park is a fun place to relax,", "play, and enjoy nature."]


def test_a_comma_after_a_very_short_start_does_not_break():
    assert lines(make(["In Atlanta, Georgia, there is a big park."])) == ["In Atlanta, Georgia,", "there is a big park."]


def test_always_breaks_at_the_end_of_a_sentence():
    assert lines(make(["Go now.", "Stay here."])) == ["Go now.", "Stay here."]


def test_breaks_at_the_sentence_boundary_even_with_no_punctuation_on_the_word():
    words = [mk("one", 0, 0, 0), mk("two", 0, 0, 1), mk("three", 1, 0, 2)]
    assert lines(words) == ["one two", "three"]


def test_caps_a_run_of_words_with_no_punctuation_at_ten():
    words = make(["one two three four five six seven eight nine ten eleven twelve"])
    assert lines(words) == ["one two three four five six seven eight nine ten", "eleven twelve"]


def test_the_word_count_restarts_after_every_break():
    words = make(["a b c d e f g h i j k l m n o p q r s t u"])
    assert [len(line.split()) for line in lines(words)] == [10, 10, 1]


def test_colons_and_semicolons_break_like_commas():
    assert lines(make(["She packed three things: a map, a hat and water."])) == ["She packed three things:", "a map, a hat and water."]


def test_dashes_break_like_commas_even_with_closing_quotes():
    assert lines(make(["He thought about it for a while— then left."])) == ["He thought about it for a while—", "then left."]
    assert lines(make(["She said “okay,” and then she left."])) == ["She said “okay,”", "and then she left."]


def test_questions_and_exclamations_end_a_line():
    assert lines(make(["Where can people go? They can go to a park!"])) == ["Where can people go?", "They can go to a park!"]


def test_empty_input_is_safe():
    assert phrase_ends([]) == []


def test_every_word_gets_a_real_boolean_and_the_last_word_ends_a_phrase():
    flagged = phrase_ends(make(["Go now.", "Stay here"]))
    assert all(isinstance(w["phraseEnd"], bool) for w in flagged)
    assert flagged[-1]["phraseEnd"] is True


def test_does_not_mutate_its_input_and_keeps_every_other_field():
    original = [{"i": 0, "text": "Go", "sentence": 0, "paragraph": 0, "start_ms": 5, "end_ms": 9, "aligned": True, "vocabId": "7"},
                {"i": 1, "text": "now.", "sentence": 0, "paragraph": 0, "start_ms": 9, "end_ms": 20, "aligned": False}]
    before = json.loads(json.dumps(original))
    result = phrase_ends(tuple(original))
    assert original == before and "phraseEnd" not in original[0]
    assert result[0] is not original[0]
    assert {k: v for k, v in result[0].items() if k != "phraseEnd"} == original[0]


def test_build_timing_adds_the_flags():
    import numpy as np

    from artifacts import build_timing
    from pipeline import Generated

    words = tuple(make(["Go now, please stay here."]))
    result = Generated(audio=np.zeros(1, dtype=np.float32), words=words, seconds_of_audio=1.0, seconds_to_generate=0.1, characters=5, unaligned_words=0)

    class E:
        name, voice = "fake", "v"

    timing = build_timing({"uuid": "p", "title": "T"}, E(), result, {})
    assert all("phraseEnd" in w for w in timing["words"])
    assert all("phraseEnd" not in w for w in words)  # the Generated result is left untouched


def test_the_human_variant_keeps_the_flags(tmp_path):
    """The human timing is built from the read-aloud timing by _retime, which must carry phraseEnd through."""
    import numpy as np

    from asr_words import Heard
    from engine import SAMPLE_RATE, SentenceAudio
    from flow import run_flow
    from word_mapper import EngineToken

    class Engine:
        name, voice = "fake", "v"

        def synthesize(self, sentence):
            ws = sentence.split()
            tokens = tuple(EngineToken(w.strip(".,"), i * 0.4, i * 0.4 + 0.3) for i, w in enumerate(ws))
            return SentenceAudio(np.full(int(0.4 * len(ws) * SAMPLE_RATE), 0.1, dtype=np.float32), tokens)

    rec = tmp_path / "rec.mp3"
    rec.write_bytes(b"audio")
    spoken = [Heard(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate("one two three four five six".split())]
    out = run_flow({"uuid": "ai", "title": "T", "content": "<p>One two three, four five six.</p>", "humanPassageId": "hu"}, Engine(),
                   recording_path=str(rec), transcribe_fn=lambda audio: spoken, decode_fn=lambda path, rate: np.zeros(24000 * 5, dtype=np.float32))
    assert [w["phraseEnd"] for w in out.human.timing["words"]] == [w["phraseEnd"] for w in out.ai.timing["words"]]
    assert out.human.timing["words"][2]["phraseEnd"] is True  # "three,"


JS = """
import { phraseLines } from "%s";
const words = JSON.parse(process.argv[1]);
const lines = phraseLines(words).map((line) => line.map((w) => w.i));
process.stdout.write(JSON.stringify(lines));
"""


def passage_words():
    sys.path.insert(0, str(ROOT / "services" / "parse"))
    from tokenizer import tokenize_html

    for sample in sorted((ROOT / "samples").glob("*.json")):
        passage = json.loads(sample.read_text(encoding="utf-8"))
        yield passage["title"], [{"i": t.i, "text": t.text, "sentence": t.sentence, "paragraph": t.paragraph} for t in tokenize_html(passage["content"])]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_python_flags_give_the_same_lines_as_the_browser_rule():
    """Run the REAL web/src/phrases.js fallback (no flags) on every sample passage and compare line by line."""
    module = (ROOT / "web" / "src" / "phrases.js").as_uri()
    checked = 0
    for title, words in passage_words():
        browser = json.loads(subprocess.run(["node", "--input-type=module", "-e", JS % module, json.dumps(words)],
                                            capture_output=True, text=True, check=True).stdout)
        flagged = phrase_ends(words)
        mine, current = [], []
        for index, w in enumerate(flagged):
            current.append(w["i"])
            nxt = flagged[index + 1] if index + 1 < len(flagged) else None
            if nxt is None or nxt["sentence"] != w["sentence"] or w["phraseEnd"]:
                mine.append(current)
                current = []
        assert mine == browser, f"{title}: Python and browser lines differ"
        checked += len(words)
    assert checked > 1500
