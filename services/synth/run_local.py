"""Generate audio + word timing for one passage, locally.

CLI:  python run_local.py <job-input.json> <data_dir>
Prints JSON lines on stdout: {"step": ...} progress lines, then one {"result": {...}} line.

The input file is the job input described in docs/API.md ("Job input file"): uuid, title, content (HTML) and
optionally settings (voice, speed, mp3Kbps), pronunciations, recording {path}, humanPassageId, qualityCheck and
vocab (ReadWorks shape). Everything a teacher can change arrives through this file, not through code.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

from engine import SAMPLE_RATE
from engines import create_engine
from fingerprint import fingerprint
from flow import Variant, run_flow
from mp3 import encode_mp3, resolve_kbps


def _emit_step(step: str) -> None:
    sys.stdout.write(json.dumps({"step": step}) + "\n")
    sys.stdout.flush()


def _write_variant(variant: Variant, data_dir: Path, kbps: int) -> None:
    (data_dir / f"{variant.id}.mp3").write_bytes(encode_mp3(variant.audio, SAMPLE_RATE, kbps))
    timing_file = data_dir / f"{variant.id}.timing.json"
    timing = variant.timing
    if "pairId" not in timing and timing_file.exists():
        # regenerating the AI voice of a passage that already has a human pair must not break that link
        existing = json.loads(timing_file.read_text()).get("pairId")
        if existing:
            timing = {**timing, "pairId": existing}
    timing_file.write_text(json.dumps(timing, ensure_ascii=False))


def _unchanged(passage: dict[str, Any], data_dir: Path, fp: str) -> dict[str, Any] | None:
    """The previous output when its fingerprint matches (same text, voice, settings, relevant fixes, recording)."""
    timing_file = data_dir / f"{passage['uuid']}.timing.json"
    if passage.get("force") or not timing_file.exists() or not (data_dir / f"{passage['uuid']}.mp3").exists():
        return None
    previous = json.loads(timing_file.read_text())
    return previous if previous.get("generatedWith", {}).get("hash") == fp else None


def publish_cards(passage: dict[str, Any], data_dir: Path, enrich_fn=None) -> bool:
    """Place cards and pictures for a teacher-generated passage, written next to the audio. Best effort: never raises, so the audio
    that is already published is never lost to a slow or blocked network."""
    try:
        from enrich_places import enrich_places, ner_places, write_enriched
        from word_pictures import word_picture_cards

        enriched = enrich_fn(passage) if enrich_fn else enrich_places({**passage, "source": passage.get("source") or "generated"}, ner=ner_places, words=word_picture_cards)
        return bool(enriched and write_enriched(data_dir, passage["uuid"], enriched))
    except Exception as err:  # noqa: BLE001
        sys.stderr.write(f"place cards skipped: {err}\n")
        return False


def run(passage: dict[str, Any], data_dir: Path, on_step=_emit_step) -> dict[str, Any]:
    data_dir.mkdir(parents=True, exist_ok=True)
    settings = passage.get("settings") or {}
    recording = (passage.get("recording") or {}).get("path")
    previous = _unchanged(passage, data_dir, fingerprint(passage, recording))
    if previous is not None:  # nothing that affects the audio changed: no generation, no cost
        return {"id": passage["uuid"], "humanPassageId": previous.get("pairId") if recording else None,
                "title": passage.get("title"), "skipped": True, **previous["metrics"]}
    engine = create_engine(settings=settings, respellings=passage.get("pronunciations"), language=passage.get("language") or "en")
    result = run_flow(passage, engine, on_step, recording_path=recording)

    on_step("publish")
    kbps = resolve_kbps(settings.get("mp3Kbps"))
    _write_variant(result.ai, data_dir, kbps)
    if result.human:
        _write_variant(result.human, data_dir, kbps)
    (data_dir / f"{result.ai.id}.soundalong.json").write_text(json.dumps(result.soundalong, ensure_ascii=False))
    publish_cards(passage, data_dir)
    return {
        "id": result.ai.id,
        "humanPassageId": result.human.id if result.human else None,
        "title": passage.get("title"),
        **result.ai.timing["metrics"],
    }


def translate_after_publish(passage: dict[str, Any], data_dir: Path, summary: dict[str, Any]) -> Optional[str]:
    """The other-language version of a teacher's passage, made AFTER the original is published (so the teacher is never kept waiting).
    Best effort: any failure leaves the original untouched. Returns the translated passage id or None."""
    try:
        from translate_flow import other_language, publish_translation, should_translate

        if not should_translate(passage):
            return None
        ids = [summary["id"], *([summary["humanPassageId"]] if summary.get("humanPassageId") else [])]
        return publish_translation({**passage, "uuid": summary["id"]}, data_dir, other_language(passage.get("language")), source_ids=ids, safe=True)
    except Exception as err:  # noqa: BLE001
        sys.stderr.write(f"translation skipped: {err}\n")
        return None


def main(passage_path: str, data_dir: str) -> int:
    passage = json.loads(Path(passage_path).read_text())
    summary = run(passage, Path(data_dir))
    sys.stdout.write(json.dumps({"result": summary}) + "\n")
    sys.stdout.flush()  # the app marks the job done now; the translation below continues in the background
    translate_after_publish(passage, Path(data_dir), summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
