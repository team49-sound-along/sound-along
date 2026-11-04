import io
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import polly_rating_pack as p


class FakePolly:
    def __init__(self):
        self.calls = []

    def synthesize_speech(self, **kwargs):
        self.calls.append(kwargs)
        pcm = (np.sin(np.linspace(0, 400, 16000)) * 8000).astype("<i2").tobytes()  # one second of tone
        return {"AudioStream": io.BytesIO(pcm)}


def test_the_plan_is_every_spanish_voice_and_engine_and_nothing_else():
    pairs = p.plan()
    assert ("Lupe", "neural") in pairs and ("Lupe", "generative") in pairs and ("Alba", "long-form") in pairs and ("Carlos", "generative") in pairs
    assert not any(v in ("Joanna", "Matthew", "Ruth") for v, _ in pairs) and all(e != "standard" for _, e in pairs)
    assert len(pairs) == len(set(pairs))


def test_the_cost_estimate_uses_the_price_of_each_engine():
    assert p.estimate_usd([("Lupe", "neural")], 1_000_000) == 16 and p.estimate_usd([("Alba", "long-form")], 10_000) == 1.0


def test_the_passage_is_cut_at_a_sentence_end_under_the_limit():
    text = p.passage_text(max_chars=300)
    assert 0 < len(text) <= 300 and text[-1] in ".!?"


def test_the_pack_has_shuffled_numbered_clips_and_the_key_is_kept_outside_the_folder(tmp_path):
    out, key_file = tmp_path / "pack", tmp_path / "KEY.txt"
    fake = FakePolly()
    key = p.build(fake, "Hola mundo. Adiós.", out, key_file)
    assert len(key) == len(p.plan()) and sorted(c.name for c in (out / "clips").iterdir()) == sorted(f"Voice-{i}.mp3" for i in range(1, len(key) + 1))
    assert all((out / "clips" / f"{c}.mp3").stat().st_size > 1000 for c, _, _ in key)
    assert not (out / "KEY.txt").exists() and key_file.exists() and "Amazon Polly" in key_file.read_text()
    assert [v for _, v, _ in key] != [v for v, _ in p.plan()]  # shuffled, so the clip number does not reveal the voice
    assert all(call["OutputFormat"] == "pcm" and "SpeechMarkTypes" not in call for call in fake.calls)  # audio only: one request per sentence
    assert "Human or computer" in (out / "READ ME FIRST - rating sheet.md").read_text()
