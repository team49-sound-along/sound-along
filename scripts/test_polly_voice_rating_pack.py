import io
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import polly_voice_rating_pack as p
from build_voice_samples import TEXT
from mp3 import encode_mp3


class FakePolly:
    def __init__(self):
        self.calls = []

    def synthesize_speech(self, **kwargs):
        self.calls.append(kwargs)
        pcm = (np.sin(np.linspace(0, 400, 16000)) * 8000).astype("<i2").tobytes()
        return {"AudioStream": io.BytesIO(pcm)}


@pytest.fixture
def samples(tmp_path):
    folder = tmp_path / "samples"
    folder.mkdir()
    tone = (np.sin(np.linspace(0, 900, 24000 * 2)) * 0.3).astype(np.float32)
    for voice, _ in p.REFERENCES["en"] + p.REFERENCES["es"]:
        (folder / f"{voice}.mp3").write_bytes(encode_mp3(tone, 24000, 48))
    return folder


def test_the_plan_has_the_references_and_every_polly_voice_and_engine_per_language():
    en, es = p.plan("en"), p.plan("es")
    assert [e.voice for e in en if e.kind == "reference"] == ["af_heart", "phonon_hadley", "phonon_everly", "phonon_bryony", "phonon_trevor"]
    assert [e.voice for e in es if e.kind == "reference"] == ["ef_dora", "em_alex"]
    pairs = {(e.voice, e.engine) for e in en + es if e.kind == "polly"}
    assert ("Ruth", "neural") in pairs and ("Ruth", "generative") in pairs and ("Gregory", "generative") not in pairs
    assert ("Lupe", "generative") in pairs and ("Carlos", "generative") in pairs and ("Carlos", "neural") not in pairs and ("Andres", "neural") in pairs
    assert not any(e.voice in ("Lucia", "Sergio", "Alba") for e in en + es), "no Castilian, UK, Australian or Indian voices"
    assert all(e.group in ("same", "mixed") for e in en + es) and all(e.group == "same" for e in en + es if e.kind == "reference")


def test_polly_reads_exactly_the_sentences_of_the_reference_clips(tmp_path, samples):
    fake = FakePolly()
    p.build(fake, tmp_path / "pack", tmp_path / "KEY.csv", samples_dir=samples)
    spoken = {c["Text"] for c in fake.calls if c["TextType"] == "text"}
    for lang in ("en", "es"):
        assert set(TEXT[lang]) <= spoken


def test_the_mixed_sentences_use_a_lang_tag_for_the_foreign_word(tmp_path, samples):
    fake = FakePolly()
    p.build(fake, tmp_path / "pack", tmp_path / "KEY.csv", samples_dir=samples)
    ssml = [c["Text"] for c in fake.calls if c["TextType"] == "ssml"]
    assert any('xml:lang="es-US"' in t and "Marisol" in t for t in ssml)
    assert any('xml:lang="en-US"' in t and "soccer" in t for t in ssml)
    assert all(c["Engine"] in ("neural", "generative") and c["OutputFormat"] == "pcm" and "SpeechMarkTypes" not in c for c in fake.calls)


def test_the_pack_is_blind_references_and_polly_share_one_format_and_the_key_is_outside(tmp_path, samples):
    out, key_file = tmp_path / "pack", tmp_path / "KEY.csv"
    clips, missing = p.build(FakePolly(), out, key_file, samples_dir=samples)
    assert missing == []
    files = sorted(f for f in out.rglob("*.mp3"))
    assert len(files) == len(clips) == len(p.plan("en")) + len(p.plan("es"))
    assert all(f.stat().st_size > 1000 for f in files)
    assert all(len(f.stem) == 4 and f.stem.isalnum() for f in files) and len({f.stem for f in files}) == len(files)
    assert not any(c.entry.voice.lower() in f.name.lower() for f in files for c in clips)
    assert key_file.exists() and not list(out.rglob("*KEY*"))
    key = p.read_key(key_file)
    assert {r["kind"] for r in key} == {"reference", "polly"} and {r["voice"] for r in key} >= {"af_heart", "ef_dora", "Ruth", "Mia"}
    assert (out / "en" / "rating-sheet.csv").exists() and "Human or computer" in (out / "es" / "READ ME FIRST - rating sheet.md").read_text()


def test_a_missing_reference_file_is_reported_and_the_rest_is_built(tmp_path, samples):
    (samples / "ef_dora.mp3").unlink()
    clips, missing = p.build(FakePolly(), tmp_path / "pack", tmp_path / "KEY.csv", samples_dir=samples)
    assert missing == ["ef_dora"] and "ef_dora" not in {c.entry.voice for c in clips}


def test_codes_are_unique_random_and_reproducible():
    codes = p.make_codes(200, seed=1)
    assert len(set(codes)) == 200 and codes == p.make_codes(200, seed=1) and codes != p.make_codes(200, seed=2)


def test_only_polly_clips_are_billed_in_the_estimate_and_a_dry_run_calls_nothing(capsys):
    en = p.plan("en")
    assert p.estimate([e for e in en if e.kind == "reference"]) == 0 and p.estimate(en) > 0
    assert p.main(["--dry-run"]) == 0
    assert "clips" in capsys.readouterr().out


# ---- objective naturalness: ranking and summary with fake scores -------------------------------------------------------------------
def rows():
    r = lambda voice, engine, lang, kind, score, group="same": {"voice": voice, "engine": engine, "language": lang, "group": group, "kind": kind, "score": score}
    return [
        r("af_heart", "kokoro", "en", "reference", 4.1), r("phonon_hadley", "phonon", "en", "reference", 3.9),
        r("Ruth", "generative", "en", "polly", 4.3), r("Ruth", "neural", "en", "polly", 3.7), r("Kevin", "neural", "en", "polly", 3.0),
        r("Ruth", "neural", "en", "polly", 1.0, group="mixed"),
        r("ef_dora", "kokoro", "es", "reference", 3.2), r("Lupe", "neural", "es", "polly", 3.4),
    ]


def test_ranking_is_best_first_and_ignores_mixed_clips():
    en = p.ranked(rows(), "en")
    assert [(x["voice"], x["engine"]) for x in en] == [("Ruth", "generative"), ("af_heart", "kokoro"), ("phonon_hadley", "phonon"), ("Ruth", "neural"), ("Kevin", "neural")]


def test_the_summary_marks_references_and_says_which_polly_voices_are_above_or_below():
    text = "\n".join(p.summary_lines(rows()))
    assert "* af_heart (kokoro)" in text and "  Kevin (neural)" in text
    assert "Best reference: af_heart (4.10). Polly voices above it: Ruth. At or below it: Kevin." in text
    assert "Best reference: ef_dora (3.20). Polly voices above it: Lupe." in text
    assert "indicative" in text


def test_the_scores_csv_has_voice_engine_language_and_score(tmp_path):
    path = tmp_path / "scores.csv"
    p.write_scores_csv(path, rows())
    lines = path.read_text().splitlines()
    assert lines[0] == "voice,engine,language,group,kind,score" and "Ruth,generative,en,same,polly,4.3" in lines


def test_scores_come_from_the_scorer_for_every_clip_and_missing_scores_are_left_out(tmp_path, samples):
    clips, _ = p.build(FakePolly(), tmp_path / "pack", tmp_path / "KEY.csv", samples_dir=samples, scorer=lambda audio: 3.14159)
    assert all(c.score == 3.142 for c in clips) and len(p.score_rows(clips)) == len(clips)
    clips, _ = p.build(FakePolly(), tmp_path / "pack2", tmp_path / "KEY2.csv", samples_dir=samples, scorer=None)
    assert p.score_rows(clips) == []


def test_when_the_naturalness_model_cannot_load_the_script_says_so_and_goes_on(monkeypatch):
    import quality_lab

    def boom():
        raise RuntimeError("no network")

    monkeypatch.setattr(quality_lab, "load_predictor", boom)
    scorer, message = p.load_scorer()
    assert scorer is None and "not available" in message and "without scores" in message
