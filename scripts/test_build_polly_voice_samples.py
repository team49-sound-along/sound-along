import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import build_polly_voice_samples as b
from build_voice_samples import TEXT


class FakePolly:
    def __init__(self, fail=()):
        self.calls, self.fail = [], set(fail)

    def synthesize_speech(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["VoiceId"] in self.fail:
            raise RuntimeError("throttled")
        return {"AudioStream": io.BytesIO(b"ID3" + kwargs["VoiceId"].encode() * 50)}


def test_every_listed_voice_gets_a_polly_prefixed_mp3_and_a_manifest(tmp_path):
    fake = FakePolly()
    manifest = b.build(fake, out_dir=tmp_path)
    listed = [v for v in json.loads(b.VOICES_FILE.read_text())]
    assert set(manifest) == {v["id"] for v in listed} and len(fake.calls) == len(listed)
    for vid in manifest:
        assert (tmp_path / f"polly-{vid}.mp3").read_bytes().startswith(b"ID3")
    assert json.loads((tmp_path / "polly-manifest.json").read_text()) == manifest


def test_the_request_is_mp3_at_24khz_with_the_shared_sentences_in_the_voice_language(tmp_path):
    fake = FakePolly()
    b.build(fake, ["Ruth", "Mia"], out_dir=tmp_path)
    ruth, mia = fake.calls
    assert (ruth["OutputFormat"], ruth["SampleRate"], ruth["Text"]) == ("mp3", "24000", " ".join(TEXT["en"]))
    assert mia["Text"] == " ".join(TEXT["es"]) and mia["VoiceId"] == "Mia"


def test_neural_is_used_when_the_voice_has_it_otherwise_generative(tmp_path):
    fake = FakePolly()
    b.build(fake, ["Ruth", "Carlos"], out_dir=tmp_path)
    assert {c["VoiceId"]: c["Engine"] for c in fake.calls} == {"Ruth": "neural", "Carlos": "generative"}


def test_a_failing_voice_is_skipped_and_the_others_are_still_written(tmp_path, capsys):
    manifest = b.build(FakePolly(fail={"Ruth"}), ["Ruth", "Joanna"], out_dir=tmp_path)
    assert list(manifest) == ["Joanna"] and not (tmp_path / "polly-Ruth.mp3").exists()
    assert "skip Ruth" in capsys.readouterr().out


def test_empty_audio_counts_as_a_failure(tmp_path):
    class Empty(FakePolly):
        def synthesize_speech(self, **kwargs):
            return {"AudioStream": io.BytesIO(b"")}

    assert b.build(Empty(), ["Ruth"], out_dir=tmp_path) == {}


def test_without_credentials_nothing_is_called(monkeypatch):
    import types

    fake_boto3 = types.SimpleNamespace(Session=lambda: types.SimpleNamespace(get_credentials=lambda: None))
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    with pytest.raises(SystemExit, match="No AWS credentials"):
        b.make_client()
