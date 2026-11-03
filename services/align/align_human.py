"""Add highlighting to an EXISTING human narration (no TTS, no regenerated audio).

  python align_human.py <passage.json> <human.mp3> <data_dir>

Writes <data_dir>/<humanId>.mp3 and .timing.json, and links it to the passage's AI-voice variant (if present in
<data_dir>) through ``pairId`` on both timing documents so the reader can offer a Human / AI voice toggle.
Prints one JSON line with the result.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "parse"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "synth"))

from artifacts import vocab_from_words  # noqa: E402
from human_alignment import align_words  # noqa: E402
from quality_lab import decode_16k, transcribe  # noqa: E402
from tokenizer import Token, tokenize_html  # noqa: E402

HUMAN_NAMESPACE = uuid.UUID("5f0d1c1e-6a53-4d7b-9a73-0a4f4c8f2b11")
NARRATOR_LABEL = "ReadWorks narrator"


def human_id(passage_id: str) -> str:
    return str(uuid.uuid5(HUMAN_NAMESPACE, passage_id))


def audio_seconds(mp3: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(out.strip())


def build_words(tokens: list[Token], aligned: list) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for token, word in zip(tokens, aligned):
        entry: dict[str, Any] = {
            "i": token.i,
            "text": token.text,
            "start_ms": round(word.start_s * 1000),
            "end_ms": round(word.end_s * 1000),
            "sentence": token.sentence,
            "paragraph": token.paragraph,
            "aligned": word.aligned,
        }
        if token.vocab_sense_id is not None:
            entry["vocabId"] = token.vocab_sense_id
        words.append(entry)
    return words


def _link_pair(data_dir: Path, ai_id: str, human: str) -> None:
    ai_file = data_dir / f"{ai_id}.timing.json"
    if not ai_file.exists():
        return
    doc = json.loads(ai_file.read_text())
    ai_file.write_text(json.dumps({**doc, "pairId": human}, ensure_ascii=False))


def run(passage: dict[str, Any], human_mp3: Path, data_dir: Path) -> dict[str, Any]:
    started = time.perf_counter()
    tokens = tokenize_html(passage["content"])
    heard = transcribe(decode_16k(str(human_mp3)))
    aligned = align_words([t.text for t in tokens], heard)
    words = build_words(tokens, aligned)

    ai_id = passage["uuid"]
    hid = human_id(ai_id)
    data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(human_mp3, data_dir / f"{hid}.mp3")
    seconds = audio_seconds(human_mp3)
    unaligned = sum(1 for w in words if not w["aligned"])
    elapsed = time.perf_counter() - started
    metrics = {
        "characters": sum(len(w["text"]) + 1 for w in words),
        "words": len(words),
        "audioSeconds": round(seconds, 2),
        "generateSeconds": round(elapsed, 2),
        "realTimeFactor": round(elapsed / max(seconds, 0.001), 3),
        "unalignedWords": unaligned,
        "pollyNeuralUsd": 0,
        "pollyStandardUsd": 0,
        "estimatedLambdaUsd": 0,
        "estimateBasis": "Existing human recording: alignment only, no speech synthesis",
    }
    timing = {
        "id": hid,
        "title": passage.get("title"),
        "engine": "human",
        "voice": NARRATOR_LABEL,
        "pairId": ai_id,
        "duration_ms": round(seconds * 1000),
        "metrics": metrics,
        "vocab": vocab_from_words(passage, words),
        "words": words,
    }
    (data_dir / f"{hid}.timing.json").write_text(json.dumps(timing, ensure_ascii=False))
    _link_pair(data_dir, ai_id, hid)
    return {"id": hid, "pairId": ai_id, "title": passage.get("title"), "words": len(words), "unalignedWords": unaligned}


def main(passage_path: str, mp3_path: str, data_dir: str) -> int:
    passage = json.loads(Path(passage_path).read_text())
    sys.stdout.write(json.dumps(run(passage, Path(mp3_path), Path(data_dir))) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
