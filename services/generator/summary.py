"""PASSAGE summary derivation, mirroring services/api/src/catalog.js (list())."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from series import clean_series


INDEX_HIDDEN = ("pk", "sk", "metrics", "review")


def index_entry(item: dict[str, Any]) -> dict[str, Any]:
    """One entry of data/index.json: the public Passage fields only (same as GET /api/passages)."""
    entry = {k: v for k, v in item.items() if k not in INDEX_HIDDEN}
    return {**entry, "pairId": entry.get("pairId"), "language": entry.get("language") or "en", "translations": entry.get("translations") or {}, "translationOf": entry.get("translationOf"), "series": entry.get("series")}


def distinct_vocab_words(vocab: dict[str, Any] | None) -> int:
    """Vocabulary words in a timing document. Its keys are word senses, so "tax" (noun) and "tax" (verb) are one word.
    Same rule as services/api/src/passageSummary.js."""
    return len({str((entry or {}).get("word") or "").strip().lower() for entry in (vocab or {}).values()} - {""})


def passage_summary(timing: dict[str, Any], created_at: str, source: str = "generated") -> dict[str, Any]:
    metrics = timing.get("metrics") or {}
    words = metrics.get("words")
    extra = {k: timing[k] for k in ("pairId", "review") if timing.get(k)}
    if timing.get("held"):
        extra["held"] = True  # its translation is still being made: kept out of the Library until then (see ready_entries)
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
        "series": clean_series(timing.get("series")),
        "metrics": metrics,
        **extra,
    }


STALE_SECONDS = 30 * 60  # a document that stopped changing this long ago is listed as it is (a part failed, or a step never finished)


def _age_seconds(entry: dict[str, Any], now: datetime) -> float:
    try:
        return (now - datetime.fromisoformat(str(entry["createdAt"]).replace("Z", "+00:00"))).total_seconds()
    except (KeyError, ValueError):
        return STALE_SECONDS  # no usable time: never hide it


def ready_entries(entries: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    """The entries that are ready to read. Mirrors services/api/src/readiness.js: a held passage, a part of a long document whose other parts are not
    all there (and unheld) yet, and a translation whose original is not ready are kept out. No marker means ready, so older data is never hidden."""
    now = now or datetime.now(timezone.utc)
    by_id = {e["id"]: e for e in entries if e.get("id")}
    held = lambda e: bool(e.get("held")) and _age_seconds(e, now) < STALE_SECONDS  # noqa: E731
    memo: dict[str, bool] = {}

    def ready(e: dict[str, Any], trail: frozenset[str] = frozenset()) -> bool:
        if e["id"] in memo:
            return memo[e["id"]]
        if e["id"] in trail:
            return True
        ok = not held(e)
        if ok and e.get("translationOf"):
            original = by_id.get(e["translationOf"])
            ok = original is None or ready(original, trail | {e["id"]})
        elif ok and e.get("series"):
            parts = [by_id.get(i) for i in e["series"]["partIds"]]
            recent = min((_age_seconds(p, now) for p in parts if p), default=STALE_SECONDS) < STALE_SECONDS
            ok = not recent or all(p is not None and not held(p) for p in parts)
        memo[e["id"]] = ok
        return ok

    return [e for e in entries if ready(e)]
