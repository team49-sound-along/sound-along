"""One spaCy pipeline per process (loading takes about a second), shared by place detection and word pictures.

The parser is switched off (not needed). The generator image already ships spaCy and en_core_web_sm for Kokoro's grapheme-to-phoneme step.
"""
from __future__ import annotations

import threading
from typing import Any

_LOCK = threading.Lock()
_NLP: dict[str, Any] = {}


def shared_nlp() -> Any:
    with _LOCK:
        if "nlp" not in _NLP:
            import spacy

            _NLP["nlp"] = spacy.load("en_core_web_sm", disable=["parser"])
        return _NLP["nlp"]
