"""Make the "Hear it" samples of the Amazon Polly voices offered in Settings.

    AWS_PROFILE=<profile> python3 scripts/build_polly_voice_samples.py [VoiceId ...]

Reads services/api/config/polly-voices.json and, for each voice, asks Polly (OutputFormat mp3, 24 kHz, mono) to read the same two short sentences
that scripts/build_voice_samples.py uses for the other voices. Writes web/public/voice-samples/polly-<VoiceId>.mp3 and polly-manifest.json.
A voice that fails is skipped with a message; with no AWS credentials nothing is called. Neural is used when the voice has it, else generative.
Polly's SynthesizeSpeech is the only call made (about 120 characters per voice).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_voice_samples import TEXT  # noqa: E402  (the sentences of every other voice sample)

VOICES_FILE = ROOT / "services" / "api" / "config" / "polly-voices.json"
OUT = ROOT / "web" / "public" / "voice-samples"
SAMPLE_RATE = "24000"
MANIFEST = "polly-manifest.json"


def sample_engine(voice: dict[str, Any]) -> str:
    return "neural" if "neural" in voice["engines"] else voice["engines"][0]


def render(client: Any, voice: dict[str, Any]) -> bytes:
    """One Polly request: the voice reads its language's two sample sentences. Returns the MP3 bytes."""
    response = client.synthesize_speech(
        Text=" ".join(TEXT[voice["lang"]]),
        VoiceId=voice["id"],
        Engine=sample_engine(voice),
        OutputFormat="mp3",
        SampleRate=SAMPLE_RATE,
        TextType="text",
    )
    data = response["AudioStream"].read()
    if not data:
        raise ValueError("Polly returned no audio")
    return data


def build(client: Any, wanted: Sequence[str] = (), out_dir: Path = OUT, voices_file: Path = VOICES_FILE) -> dict[str, Any]:
    """Make the samples. Returns the manifest {VoiceId: {file, engine, language, text, bytes}} of the voices that succeeded (also written to out_dir)."""
    voices = [v for v in json.loads(voices_file.read_text()) if v.get("engine") == "polly" and (not wanted or v["id"] in wanted)]
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {}
    for voice in voices:
        try:
            data = render(client, voice)
        except Exception as err:  # noqa: BLE001
            print("skip", voice["id"], f"({type(err).__name__}: {str(err)[:80]})", flush=True)
            continue
        name = f"polly-{voice['id']}.mp3"
        (out_dir / name).write_bytes(data)
        manifest[voice["id"]] = {"file": name, "engine": sample_engine(voice), "language": voice["accent"], "text": " ".join(TEXT[voice["lang"]]), "bytes": len(data)}
        print("ok  ", voice["id"], flush=True)
    (out_dir / MANIFEST).write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    return manifest


def make_client(region: str = "us-west-2") -> Any:
    """A Polly client, or a clear SystemExit message when boto3 or credentials are missing (nothing is called)."""
    try:
        import boto3
    except ImportError:
        raise SystemExit("boto3 is not installed here. Use a Python with boto3 (for example python3) and AWS credentials.") from None
    if boto3.Session().get_credentials() is None:
        raise SystemExit("No AWS credentials found. Set AWS_PROFILE (or the usual AWS_* variables) and run again; nothing was called.")
    return boto3.client("polly", region_name=region)


def main(argv: Sequence[str]) -> int:
    wanted = [a for a in argv if not a.startswith("-")]
    manifest = build(make_client(), wanted)
    expected = [v for v in json.loads(VOICES_FILE.read_text()) if v.get("engine") == "polly" and (not wanted or v["id"] in wanted)]
    print(f"{len(manifest)} of {len(expected)} samples written to {OUT}")
    return 0 if len(manifest) == len(expected) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
