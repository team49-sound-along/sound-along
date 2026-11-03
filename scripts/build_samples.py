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
import uuid
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
TEA = "5af24980-4d6d-41c1-87fa-4f21cb2d169d"
# ReadWorks' own product JSON flags passages that have a human recording with "hau" (Park and Tea Party have it;
# the Polly-read Pride and Prejudice passage does not). The audio files are public on their CDN.
HUMAN_TEA_URL = f"{CDN}/A_Very_Messy_Tea_Party_1548193857_1_{TEA}.mp3"


def log(message: str) -> None:
    sys.stdout.write(message + "\n")
    sys.stdout.flush()


def download(url: str, target: Path) -> Path:
    log(f"  downloading {url.rsplit('/', 1)[-1]}")
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 (fixed https URLs above)
        target.write_bytes(response.read())
    return target


# Stable ids for the human-narrated variants (the Park Caretaker one keeps the id used since the first build).
HUMAN_NAMESPACE = uuid.UUID("5f0d1c1e-6a53-4d7b-9a73-0a4f4c8f2b11")


def human_id(ai_id: str) -> str:
    return str(uuid.uuid5(HUMAN_NAMESPACE, ai_id))


def job_input(sample: dict, recording: Path | None) -> dict:
    """The same job input file the API writes for a teacher's passage (docs/API.md), built from a bundled sample."""
    return {
        "uuid": sample["uuid"], "title": sample["title"], "content": sample["content"], "vocab": sample.get("vocab"),
        "source": "sample",
        "settings": {"voice": "af_heart", "speed": 0.95, "mp3Kbps": 48},
        "pronunciations": json.loads((ROOT / "services/synth/pronunciations.json").read_text()),
        "recording": {"path": str(recording)} if recording else None,
        "humanPassageId": human_id(sample["uuid"]) if recording else None,
        "qualityCheck": True,
    }


def generate(passage_file: Path, recording: Path | None, workdir: Path) -> None:
    sample = json.loads(passage_file.read_text())
    payload = job_input(sample, recording)
    payload["pronunciations"] = {k: v for k, v in payload["pronunciations"].items() if not k.startswith("_")}

    # Stored source, kept so the passage can be regenerated later with new settings or pronunciation fixes. It has no
    # recording path (that file only exists during this build); regenerating keeps the existing human variant and link.
    stored = DATA / "raw" / f"{sample['uuid']}.json"
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_text(json.dumps({**payload, "recording": None}, ensure_ascii=False))

    # The run itself gets its own input file, WITH the recording, so the human variant is produced.
    run_input = workdir / f"{sample['uuid']}.run.json"
    run_input.write_text(json.dumps(payload, ensure_ascii=False))
    subprocess.run([sys.executable, str(ROOT / "services/synth/run_local.py"), str(run_input), str(DATA)], check=True, stdout=subprocess.DEVNULL)


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
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        log(f"1/4 generating {len(passages)} passages; the Park Caretaker and Tea Party ones also align their existing human recordings")
        human_mp3 = download(HUMAN_PARK_URL, workdir / "park_human.mp3")
        recordings = {PARK: human_mp3, TEA: download(HUMAN_TEA_URL, workdir / "tea_human.mp3")}
        for passage_file in passages:
            generate(passage_file, recordings.get(passage_file.stem), workdir)
        log("2/4 done")

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
            human = human_mp3
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
