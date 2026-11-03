"""PASSAGE summary derivation, mirroring services/api/src/catalog.js (list())."""
from __future__ import annotations

from typing import Any


def passage_summary(timing: dict[str, Any], created_at: str, source: str = "generated") -> dict[str, Any]:
    metrics = timing.get("metrics") or {}
    words = metrics.get("words")
    extra = {k: timing[k] for k in ("pairId", "review") if timing.get(k)}
    return {
        "id": timing["id"],
        "title": timing.get("title") or "Untitled passage",
        "words": words if words is not None else len(timing.get("words") or []),
        "durationMs": timing.get("duration_ms") or 0,
        "engine": timing.get("engine") or "unknown",
        "voice": timing.get("voice") or "unknown",
        "createdAt": created_at,
        "source": source,
        "vocabCount": len(timing.get("vocab") or {}),
        "metrics": metrics,
        **extra,
    }
