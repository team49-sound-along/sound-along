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
from typing import Any

from engine import SAMPLE_RATE
from engines import create_engine
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


def run(passage: dict[str, Any], data_dir: Path, on_step=_emit_step) -> dict[str, Any]:
    data_dir.mkdir(parents=True, exist_ok=True)
    settings = passage.get("settings") or {}
    engine = create_engine(settings=settings, respellings=passage.get("pronunciations"))
    recording = (passage.get("recording") or {}).get("path")
    result = run_flow(passage, engine, on_step, recording_path=recording)

    on_step("publish")
    kbps = resolve_kbps(settings.get("mp3Kbps"))
    _write_variant(result.ai, data_dir, kbps)
    if result.human:
        _write_variant(result.human, data_dir, kbps)
    (data_dir / f"{result.ai.id}.soundalong.json").write_text(json.dumps(result.soundalong, ensure_ascii=False))
    return {
        "id": result.ai.id,
        "humanPassageId": result.human.id if result.human else None,
        "title": passage.get("title"),
        **result.ai.timing["metrics"],
    }


def main(passage_path: str, data_dir: str) -> int:
    passage = json.loads(Path(passage_path).read_text())
    summary = run(passage, Path(data_dir))
    sys.stdout.write(json.dumps({"result": summary}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
