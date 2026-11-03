"""Rebuild every sample artifact and every measured number from scratch, in order.

  .venv/bin/python scripts/build_samples.py [--skip-mos]

1. Generate AI-voice audio + timing for each passage in samples/ (data/).
2. Download the public ReadWorks human recording of the Park Caretaker passage and align it (Human voice variant).
3. Check every AI-voice passage against an independent Whisper transcript (word error, timing agreement).
4. Predict naturalness (UTMOS) for our audio vs the public ReadWorks human and Polly recordings.
5. Write data/quality-report.json, the file the API serves to the Insights page.

Every number quoted in the UI, README and demo should come from the files this script writes.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for sub in ("parse", "synth", "eval", "align"):
    sys.path.insert(0, str(ROOT / "services" / sub))

from qa_metrics import Expected, compare, percentile  # noqa: E402
from quality_lab import decode_16k, run_mos, transcribe  # noqa: E402

DATA = ROOT / "data"
SAMPLES = ROOT / "samples"
PARK = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98"
PRIDE = "ff1d34c9-14f1-4e78-b509-6568dc912a17"
CDN = "https://dq5qica5h7eg3.cloudfront.net/data/audio"
HUMAN_PARK_URL = f"{CDN}/Lets_Meet_a_Park_Caretaker_1786044484_1_{PARK}.mp3"
POLLY_PRIDE_URL = f"{CDN}/Excerpt_from_Pride_and_Prejudice-{PRIDE}_0001.mp3"


def log(message: str) -> None:
    sys.stdout.write(message + "\n")
    sys.stdout.flush()


def download(url: str, target: Path) -> Path:
    log(f"  downloading {url.rsplit('/', 1)[-1]}")
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 (fixed https URLs above)
        target.write_bytes(response.read())
    return target


def generate_ai(passage_file: Path) -> None:
    subprocess.run([sys.executable, str(ROOT / "services/synth/run_local.py"), str(passage_file), str(DATA)], check=True, stdout=subprocess.DEVNULL)


def align_human(workdir: Path) -> None:
    human_mp3 = download(HUMAN_PARK_URL, workdir / "park_human.mp3")
    subprocess.run(
        [sys.executable, str(ROOT / "services/align/align_human.py"), str(SAMPLES / f"{PARK}.json"), str(human_mp3), str(DATA)],
        check=True, stdout=subprocess.DEVNULL,
    )


def asr_report(passage_id: str) -> tuple[dict, tuple[float, ...]]:
    timing = json.loads((DATA / f"{passage_id}.timing.json").read_text())
    expected = [Expected(w["i"], w["text"], w["start_ms"]) for w in timing["words"]]
    report = compare(expected, transcribe(decode_16k(str(DATA / f"{passage_id}.mp3"))))
    row = {
        "id": passage_id,
        "title": timing["title"],
        "wordsChecked": report.words_checked,
        "wer": round(report.wer, 4),
        "medianErrorMs": round(report.median_error_ms or 0),
        "p95ErrorMs": round(report.p95_error_ms or 0),
        "within100ms": round(report.within_100ms or 0, 3),
        "within250ms": round(report.within_250ms or 0, 3),
        "pronunciationSuspects": [list(pair) for pair in report.substitutions][:12],
    }
    return row, report.errors_ms


def main(skip_mos: bool) -> int:
    started = time.time()
    passages = sorted(SAMPLES.glob("*.json"))
    log(f"1/4 generating AI voice for {len(passages)} passages")
    for passage_file in passages:
        generate_ai(passage_file)

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        log("2/4 aligning the existing human recording")
        align_human(workdir)

        log("3/4 checking against an independent Whisper transcript")
        rows, pooled = [], []
        for passage_file in passages:
            row, errors = asr_report(passage_file.stem)
            rows.append(row)
            pooled.extend(errors)
            log(f"  {row['title'][:34]:<34} WER {row['wer']:.3f}  median {row['medianErrorMs']} ms  p95 {row['p95ErrorMs']} ms")

        naturalness = None
        if not skip_mos:
            log("4/4 predicting naturalness (UTMOS) against public ReadWorks recordings")
            human = download(HUMAN_PARK_URL, workdir / "park_human.mp3")
            polly = download(POLLY_PRIDE_URL, workdir / "pride_polly.mp3")
            naturalness = run_mos([
                f"ai_voice_park={DATA / (PARK + '.mp3')}",
                f"readworks_human_park={human}",
                f"ai_voice_pride={DATA / (PRIDE + '.mp3')}",
                f"readworks_current_polly_pride={polly}",
            ])

    words = sum(r["wordsChecked"] for r in rows)
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "asr": {
            "method": "faster-whisper small.en transcript with word timestamps, compared with our timing. Agreement between two systems, not ground truth.",
            "passages": rows,
            "pooled": {
                "wordsChecked": words,
                "wer": round(sum(r["wer"] * r["wordsChecked"] for r in rows) / max(words, 1), 4),
                "medianErrorMs": round(percentile(list(pooled), 0.5) or 0),
                "p95ErrorMs": round(percentile(list(pooled), 0.95) or 0),
                "within100ms": round(sum(1 for e in pooled if e <= 100) / max(len(pooled), 1), 3),
                "within250ms": round(sum(1 for e in pooled if e <= 250) / max(len(pooled), 1), 3),
            },
        },
        "naturalness": None if naturalness is None else {
            "method": "UTMOS22 predicted MOS. A proxy that rewards clean audio and penalises recording noise; it is not a listening test.",
            "scores": naturalness,
        },
    }
    (DATA / "quality-report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    log(f"done in {time.time() - started:.0f}s: data/quality-report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--skip-mos" in sys.argv))
