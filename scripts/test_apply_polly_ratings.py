import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import apply_polly_ratings as a


def row(code, language, kind, voice, engine, group="same"):
    return {"code": code, "language": language, "group": group, "kind": kind, "voice": voice, "engine": engine, "accent": ""}


KEY = [
    row("AAAA", "en", "reference", "af_heart", "kokoro"), row("BBBB", "en", "reference", "phonon_hadley", "phonon"),
    row("CCCC", "en", "polly", "Ruth", "neural"), row("DDDD", "en", "polly", "Ruth", "generative"),
    row("EEEE", "en", "polly", "Kevin", "neural"), row("FFFF", "en", "polly", "Joanna", "neural"),
    row("GGGG", "es", "reference", "ef_dora", "kokoro"), row("HHHH", "es", "polly", "Lupe", "neural"),
    row("JJJJ", "en", "polly", "Ruth", "neural", group="mixed"),
]


def test_codes_for_references_and_candidates_are_accepted_together_and_scores_are_averaged():
    means = a.clip_means({"AAAA": [4, 5], "CCCC": 4.5, "DDDD": {"scores": [3, 4]}}, KEY)
    assert means == {"AAAA": 4.5, "CCCC": 4.5, "DDDD": 3.5}


def test_a_voice_is_recommended_only_at_or_above_the_best_reference_or_within_the_margin():
    ratings = {"AAAA": 4.0, "BBBB": 4.4, "CCCC": 4.5, "DDDD": 3.0, "EEEE": 3.5, "FFFF": 4.2, "GGGG": 3.0, "HHHH": 2.7}
    out = a.apply(ratings, KEY, margin=0.2)
    assert out["references"]["en"]["best"] == "phonon_hadley"
    assert out["recommended"] == ["Joanna", "Ruth"]  # Ruth above the best reference; Joanna 4.2 is within 0.2 of 4.4; Kevin 3.5 and Lupe 2.7 are not
    assert out["ratings"]["Ruth"]["qualifyingEngines"] == ["neural"] and out["ratings"]["Ruth"]["atOrAboveBestReference"] is True
    assert out["ratings"]["Joanna"]["atOrAboveBestReference"] is False
    assert out["ratings"]["Kevin"]["qualifyingEngines"] == []


def test_zero_margin_means_at_or_above_only():
    out = a.apply({"AAAA": 4.0, "CCCC": 3.9, "FFFF": 4.0}, KEY, margin=0)
    assert out["recommended"] == ["Joanna"]


def test_with_no_rated_reference_in_a_language_nothing_there_is_recommended():
    out = a.apply({"HHHH": 5, "CCCC": 5}, KEY)
    assert out["recommended"] == [] and out["references"] == {}


def test_mixed_clips_do_not_count_toward_the_rating():
    out = a.apply({"AAAA": 4.0, "JJJJ": 5, "CCCC": 3.0}, KEY)
    assert out["ratings"]["Ruth"]["engines"] == {"neural": 3.0} and out["recommended"] == []


def test_a_code_that_is_not_in_the_key_is_an_error():
    with pytest.raises(ValueError, match="ZZZZ"):
        a.clip_means({"ZZZZ": 4}, KEY)


@pytest.mark.parametrize("bad", ["good", [4, "x"], 6, 0, [], True, None])
def test_bad_scores_are_refused(bad):
    with pytest.raises(ValueError):
        a.scores_of(bad)


def test_the_script_writes_the_file_the_api_reads(tmp_path):
    from polly_voice_rating_pack import Clip, Entry, write_key

    clips = [Clip(r["code"], Entry(r["kind"], r["voice"], r["engine"], r["language"], r["group"])) for r in KEY]
    key_file, ratings_file, out = tmp_path / "key.csv", tmp_path / "ratings.json", tmp_path / "polly-voice-ratings.json"
    write_key(key_file, clips)
    ratings_file.write_text(json.dumps({"AAAA": 4.0, "CCCC": 4.1}))
    assert a.main(["--ratings", str(ratings_file), "--key", str(key_file), "--out", str(out)]) == 0
    written = json.loads(out.read_text())
    assert written["recommended"] == ["Ruth"] and written["margin"] == 0.2


def test_a_bad_ratings_file_gives_a_plain_message_and_writes_nothing(tmp_path, capsys):
    from polly_voice_rating_pack import Clip, Entry, write_key

    key_file, ratings_file, out = tmp_path / "key.csv", tmp_path / "ratings.json", tmp_path / "out.json"
    write_key(key_file, [Clip("AAAA", Entry("reference", "af_heart", "kokoro", "en", "same"))])
    ratings_file.write_text(json.dumps({"NOPE": 4}))
    assert a.main(["--ratings", str(ratings_file), "--key", str(key_file), "--out", str(out)]) == 1
    assert not out.exists() and "not in the key" in capsys.readouterr().err
