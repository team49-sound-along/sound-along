"""Engine selection: TTS_ENGINE=kokoro (default, open source) or polly (AWS-native fallback)."""
from __future__ import annotations

import os
from typing import Any, Mapping

from engine import Engine


def create_engine(
    name: str | None = None,
    settings: Mapping[str, Any] | None = None,
    respellings: Mapping[str, str] | None = None,
    language: str = "en",
) -> Engine:
    """``settings`` and ``respellings`` come from the job's input file. Without them the defaults apply
    (and, for pronunciations, the repository's pronunciations.json)."""
    if language not in ("en", "es"):
        raise ValueError(f"Unsupported language {language!r}. Use 'en' or 'es'.")
    chosen = (name or os.environ.get("TTS_ENGINE") or "kokoro").lower()
    options = settings or {}
    if chosen == "kokoro":
        from engine import KokoroEngine

        voice_key = "voice" if language == "en" else "voiceEs"
        return KokoroEngine(
            voice=options.get(voice_key) or None,
            speed=float(options.get("speed") or 0.95),
            respellings=respellings,
            language=language,
        )
    if chosen == "polly":
        import boto3

        from polly_engine import PollyEngine

        client = boto3.client("polly", region_name=os.environ.get("AWS_REGION", "us-west-2"))
        voice = os.environ.get("POLLY_VOICE", "Joanna") if language == "en" else os.environ.get("POLLY_VOICE_ES", "Lupe")
        return PollyEngine(client, voice=voice)
    raise ValueError(f"Unknown TTS_ENGINE {chosen!r}. Use 'kokoro' or 'polly'.")
