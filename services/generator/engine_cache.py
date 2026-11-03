"""Module-level lazy cache for the TTS engine (Kokoro unless TTS_ENGINE=polly) (loaded on first invocation, not at Lambda init)."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

LOG = logging.getLogger(__name__)
_engine: Any = None
_lock = threading.Lock()


def get_engine() -> Any:
    global _engine
    with _lock:
        if _engine is None:
            from engines import create_engine

            started = time.perf_counter()
            _engine = create_engine()
            LOG.info("kokoro engine loaded in %.1fs", time.perf_counter() - started)
        return _engine
