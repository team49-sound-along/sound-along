"""PASSAGE summary derivation, mirroring services/api/src/catalog.js (list())."""
from __future__ import annotations

from typing import Any


INDEX_HIDDEN = ("pk", "sk", "metrics", "review")


def index_entry(item: dict[str, Any]) -> dict[str, Any]:
    """One entry of data/index.json: the public Passage fields only (same as GET /api/passages)."""
    entry = {k: v for k, v in item.items() if k not in INDEX_HIDDEN}
    return {**entry, "pairId": entry.get("pairId"), "language": entry.get("language") or "en", "translations": entry.get("translations") or {}, "translationOf": entry.get("translationOf")}


def distinct_vocab_words(vocab: dict[str, Any] | None) -> int:
    """Vocabulary words in a timing document. Its keys are word senses, so "tax" (noun) and "tax" (verb) are one word.
    Same rule as services/api/src/passageSummary.js."""
    return len({str((entry or {}).get("word") or "").strip().lower() for entry in (vocab or {}).values()} - {""})


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
        "vocabCount": distinct_vocab_words(timing.get("vocab")),
        "language": timing.get("language") or "en",
        "translations": {lang: t["id"] for lang, t in (timing.get("translations") or {}).items() if isinstance(t, dict) and t.get("id")},
        "translationOf": (timing.get("translationOf") or {}).get("id") if isinstance(timing.get("translationOf"), dict) else None,
        "metrics": metrics,
        **extra,
    }
