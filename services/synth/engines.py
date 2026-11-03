"""Engine selection: kokoro (default, open source), phonon (chosen by a phonon_* voice) or polly (AWS-native fallback, TTS_ENGINE=polly)."""
from __future__ import annotations

import os
from typing import Any, Mapping

from engine import Engine
from pronunciations import load_respellings


def engine_for_voice(voice: str | None) -> str | None:
    """The engine a voice belongs to when it is not Kokoro's, so choosing a voice in Settings is enough."""
    from phonon_engine import PHONON_VOICES

    return "phonon" if isinstance(voice, str) and voice in PHONON_VOICES else None


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
    voice_key = "voice" if language == "en" else "voiceEs"
    if chosen == "kokoro" and engine_for_voice(options.get(voice_key)):
        if language != "en":
            raise ValueError(f"{options.get(voice_key)!r} is an English voice; choose a Spanish voice for Spanish text.")
        chosen = engine_for_voice(options.get(voice_key))  # type: ignore[assignment]
    if chosen == "phonon":
        from phonon_engine import DEFAULT_VOICE, PhononEngine

        if language != "en":
            raise ValueError("Phonon speaks English only; use Kokoro for Spanish text.")
        voice = options.get("voice") if engine_for_voice(options.get("voice")) else DEFAULT_VOICE  # TTS_ENGINE=phonon with no Phonon voice chosen
        return PhononEngine(voice=voice, respellings=load_respellings() if respellings is None else respellings)
    if chosen == "kokoro":
        from engine import KokoroEngine

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
    raise ValueError(f"Unknown TTS_ENGINE {chosen!r}. Use 'kokoro', 'phonon' or 'polly'.")
