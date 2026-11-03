"""Generate audio + word timing for one passage.

CLI:  python run_local.py <passage.json> <data_dir>
Prints JSON lines on stdout: {"step": ...} progress lines, then one {"result": {...metrics}} line.
Input passage JSON needs: uuid, title, content (HTML). Optional: vocab (ReadWorks shape).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import soundfile as sf

from engine import SAMPLE_RATE
from engines import create_engine
from artifacts import generate_artifacts, lambda_estimate, vocab_for as _vocab_for  # noqa: F401


def _mp3_kbps() -> int:
    try:
        value = int(os.environ.get("SOUND_ALONG_MP3_KBPS", "48"))
    except ValueError:
        return 48
    return value if 24 <= value <= 128 else 48


MP3_KBPS = _mp3_kbps()


def _encode_mp3(audio, mp3: Path) -> None:
    wav = mp3.with_suffix(".wav")
    sf.write(wav, audio, SAMPLE_RATE)
    # Constant bitrate: variable-bitrate MP3 seeks inaccurately in browsers.
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-ac", "1", "-codec:a", "libmp3lame", "-b:a", f"{MP3_KBPS}k", str(mp3)],
        check=True,
    )
    wav.unlink()


def _emit_step(step: str) -> None:
    sys.stdout.write(json.dumps({"step": step}) + "\n")
    sys.stdout.flush()


def run(passage: dict[str, Any], data_dir: Path, on_step=_emit_step) -> dict[str, Any]:
    data_dir.mkdir(parents=True, exist_ok=True)
    pid = passage["uuid"]
    artifacts = generate_artifacts(passage, create_engine(), on_step)
    on_step("publish")
    _encode_mp3(artifacts.audio, data_dir / f"{pid}.mp3")
    timing_file = data_dir / f"{pid}.timing.json"
    timing = artifacts.timing
    if timing_file.exists():  # regenerating the AI voice must not break the link to its human-narrated pair
        existing_pair = json.loads(timing_file.read_text()).get("pairId")
        if existing_pair:
            timing = {**timing, "pairId": existing_pair}
    timing_file.write_text(json.dumps(timing, ensure_ascii=False))
    return {"id": pid, "title": passage.get("title"), **artifacts.metrics}


def main(passage_path: str, data_dir: str) -> int:
    passage = json.loads(Path(passage_path).read_text())
    summary = run(passage, Path(data_dir))
    sys.stdout.write(json.dumps({"result": summary}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
