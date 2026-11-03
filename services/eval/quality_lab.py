"""Audio quality lab. Objective, repeatable, free checks on generated narration.

  python quality_lab.py asr <timing.json> <audio.mp3>      pronunciation suspects + timing agreement (faster-whisper)
  python quality_lab.py mos <label=audio.mp3> [...]        predicted naturalness (UTMOS22, a MOS predictor)

ASR agreement and MOS are PROXIES. They catch regressions and compare systems; they do not replace listening.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "synth"))

from asr_words import SR, Heard, decode_16k, transcribe  # noqa: E402,F401
from qa_metrics import Expected, Report, compare  # noqa: E402



def report_dict(report: Report) -> dict:
    return {
        "wordsChecked": report.words_checked,
        "wer": round(report.wer, 4),
        "substitutions": [list(pair) for pair in report.substitutions],
        "deletions": list(report.deletions),
        "insertions": report.insertions,
        "numbersSkipped": report.skipped_numeric,
        "timingPairs": report.timing_pairs,
        "medianErrorMs": None if report.median_error_ms is None else round(report.median_error_ms),
        "p95ErrorMs": None if report.p95_error_ms is None else round(report.p95_error_ms),
        "within100ms": None if report.within_100ms is None else round(report.within_100ms, 3),
        "within250ms": None if report.within_250ms is None else round(report.within_250ms, 3),
    }


def run_asr(timing_path: str, audio_path: str) -> dict:
    timing = json.loads(Path(timing_path).read_text())
    expected = [Expected(w["i"], w["text"], w["start_ms"]) for w in timing["words"]]
    heard = transcribe(decode_16k(audio_path))
    return {"title": timing.get("title"), "voice": timing.get("voice"), **report_dict(compare(expected, heard))}


def run_mos(items: list[str], window_s: int = 8) -> dict:
    import torch

    predictor = torch.hub.load("tarepan/SpeechMOS:v1.2.0", "utmos22_strong", trust_repo=True).eval()
    results: dict[str, dict] = {}
    for item in items:
        label, path = item.split("=", 1)
        audio = decode_16k(path)
        step = window_s * SR
        scores = []
        for start in range(0, max(len(audio) - SR, 1), step):
            chunk = audio[start:start + step]
            if len(chunk) < 2 * SR:
                continue
            with torch.no_grad():
                scores.append(float(predictor(torch.from_numpy(chunk).unsqueeze(0), SR)))
        results[label] = {
            "meanMos": round(float(np.mean(scores)), 3) if scores else None,
            "p10Mos": round(float(np.percentile(scores, 10)), 3) if scores else None,
            "windows": len(scores),
        }
    return results


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[1] == "asr":
        out = run_asr(argv[2], argv[3])
    elif len(argv) >= 3 and argv[1] == "mos":
        out = run_mos(argv[2:])
    else:
        sys.stderr.write(__doc__ or "")
        return 2
    sys.stdout.write(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
