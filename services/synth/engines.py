"""Engine selection: TTS_ENGINE=kokoro (default, open source) or polly (AWS-native fallback)."""
from __future__ import annotations

import os

from engine import Engine


def create_engine(name: str | None = None) -> Engine:
    chosen = (name or os.environ.get("TTS_ENGINE") or "kokoro").lower()
    if chosen == "kokoro":
        from engine import KokoroEngine

        return KokoroEngine()
    if chosen == "polly":
        import boto3

        from polly_engine import PollyEngine

        client = boto3.client("polly", region_name=os.environ.get("AWS_REGION", "us-west-2"))
        return PollyEngine(client, voice=os.environ.get("POLLY_VOICE", "Joanna"))
    raise ValueError(f"Unknown TTS_ENGINE {chosen!r}. Use 'kokoro' or 'polly'.")
