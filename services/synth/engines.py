"""Engine selection: TTS_ENGINE=kokoro (default, open source) or polly (AWS-native fallback)."""
from __future__ import annotations

import os
from typing import Any, Mapping

from engine import Engine


def create_engine(
    name: str | None = None,
    settings: Mapping[str, Any] | None = None,
    respellings: Mapping[str, str] | None = None,
) -> Engine:
    """``settings`` and ``respellings`` come from the job's input file. Without them the defaults apply
    (and, for pronunciations, the repository's pronunciations.json)."""
    chosen = (name or os.environ.get("TTS_ENGINE") or "kokoro").lower()
    options = settings or {}
    if chosen == "kokoro":
        from engine import KokoroEngine

        return KokoroEngine(
            voice=str(options.get("voice") or "af_heart"),
            speed=float(options.get("speed") or 0.95),
            respellings=respellings,
        )
    if chosen == "polly":
        import boto3

        from polly_engine import PollyEngine

        client = boto3.client("polly", region_name=os.environ.get("AWS_REGION", "us-west-2"))
        return PollyEngine(client, voice=os.environ.get("POLLY_VOICE", "Joanna"))
    raise ValueError(f"Unknown TTS_ENGINE {chosen!r}. Use 'kokoro' or 'polly'.")
