"""A stable fingerprint of everything that determines a passage's audio, so unchanged input is never generated twice.

ReadWorks must run this with a tiny team and a free product: re-submitting the same text, or changing a pronunciation fix
for a word the passage does not contain, must cost nothing. The fingerprint is stored on the output (generatedWith.hash)
and compared before any work starts. Bump PIPELINE_VERSION when a code change alters the audio or timing.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "parse"))  # repo layout and /var/task layout

from tokenizer import tokenize_html  # noqa: E402

PIPELINE_VERSION = "2026-11-03.3"
_WORD = re.compile(r"^\W+|\W+$")


def _passage_words(content: str) -> set[str]:
    return {_WORD.sub("", t.text.lower()) for t in tokenize_html(content)}


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(passage: dict[str, Any], recording_path: Optional[str] = None) -> str:
    language = passage.get("language") or "en"
    settings = passage.get("settings") or {}
    words = _passage_words(passage.get("content") or "")
    fixes = {} if language != "en" else {w: r for w, r in sorted((passage.get("pronunciations") or {}).items()) if w.lower() in words}
    parts = {
        "version": PIPELINE_VERSION,
        "content": passage.get("content") or "",
        "language": language,
        "voice": settings.get("voice" if language == "en" else "voiceEs"),
        "speed": settings.get("speed"),
        "mp3Kbps": settings.get("mp3Kbps"),
        "pronunciations": fixes,
        "qualityCheck": bool(passage.get("qualityCheck")),
        "humanPassageId": passage.get("humanPassageId") if recording_path else None,
        "recording": _file_sha256(recording_path) if recording_path else None,
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
