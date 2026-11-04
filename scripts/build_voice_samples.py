"""Render a short spoken sample of every voice, so Settings can play it when a voice is chosen.

    .venv/bin/python scripts/build_voice_samples.py [voice_id ...]

Writes web/public/voice-samples/<voice id>.mp3 (about 10 seconds each, our own synthetic audio). With no arguments it renders every voice in
services/api/config/voices.json. Voices that cannot run here (for example Polly on a machine without AWS) are skipped with a message.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "synth"))

import numpy as np  # noqa: E402

from engine import SAMPLE_RATE  # noqa: E402
from engines import create_engine  # noqa: E402
from mp3 import encode_mp3  # noqa: E402

OUT = ROOT / "web" / "public" / "voice-samples"
TEXT = {
    "en": ["Hello! This is how I sound when I read a story aloud.", "Today we are going to explore a lighthouse by the sea."],
    "es": ["¡Hola! Así sueno cuando leo un cuento en voz alta.", "Hoy vamos a explorar un faro junto al mar."],
}


def render(voice: dict) -> bytes:
    lang = voice.get("lang", "en")
    key = "voice" if lang == "en" else "voiceEs"
    engine = create_engine(settings={key: voice["id"], "speed": 0.95}, language=lang)
    pause = np.zeros(int(SAMPLE_RATE * 0.25), dtype=np.float32)
    parts = []
    for sentence in TEXT[lang]:
        parts += [np.asarray(engine.synthesize(sentence).audio, dtype=np.float32), pause]
    return encode_mp3(np.concatenate(parts), SAMPLE_RATE, 48)


def main(wanted: list[str]) -> int:
    voices = json.loads((ROOT / "services" / "api" / "config" / "voices.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    failed = 0
    for voice in voices:
        if wanted and voice["id"] not in wanted:
            continue
        try:
            (OUT / f"{voice['id']}.mp3").write_bytes(render(voice))
            print("ok  ", voice["id"], flush=True)
        except Exception as err:  # noqa: BLE001
            failed += 1
            print("skip", voice["id"], f"({type(err).__name__}: {str(err)[:80]})", flush=True)
    return 1 if failed and wanted else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
