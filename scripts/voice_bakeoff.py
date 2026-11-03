"""Rank narrator voices on the same text with measurements, so only voices that are human-like are offered.

  .venv/bin/python scripts/voice_bakeoff.py [--lang en|es] [--voices af_heart,af_bella,...]

For each voice: synthesize the SAME ~30 s of a passage, then report the predicted naturalness (UTMOS22, English speech
only) and the word error rate against the known text (faster-whisper). Both are PROXIES for listening, but they catch
voices that are clearly worse, and they are repeatable. Kokoro's authors also publish a grade per voice (VOICES.md).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for sub in ("parse", "synth", "eval"):
    sys.path.insert(0, str(ROOT / "services" / sub))

from asr_words import resample_to_16k, transcribe  # noqa: E402
from engine import SAMPLE_RATE, KokoroEngine  # noqa: E402
from flow import run_flow  # noqa: E402
from qa_metrics import Expected, compare  # noqa: E402
from quality_lab import load_predictor, mos_of  # noqa: E402

PARK = ROOT / "samples" / "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98.json"
SPANISH = ROOT / "samples" / "5e5f1d3c-7a2b-4c9e-8d1a-3b6f2c9e4a70.json"
ENGLISH_VOICES = "af_heart af_bella af_nicole af_aoede af_kore af_sarah af_sky af_nova af_alloy af_jessica af_river bf_emma bf_isabella bf_alice bf_lily am_michael am_fenrir am_puck am_adam am_echo am_eric am_liam am_onyx bm_george bm_fable bm_daniel bm_lewis".split()
SPANISH_VOICES = "ef_dora em_alex em_santa".split()


def first_paragraphs(html: str, count: int = 2) -> str:
    paragraphs = [p for p in html.split("</p>") if "<p" in p and "<figure" not in p][:count]
    return "</p>".join(paragraphs) + "</p>"


def evaluate(voice: str, language: str, content: str, predictor) -> dict:
    engine = KokoroEngine(voice=voice, language=language)
    result = run_flow({"uuid": voice, "title": voice, "language": language, "content": content}, engine)
    audio16 = resample_to_16k(result.ai.audio, SAMPLE_RATE)
    heard = transcribe(audio16, language=language)
    words = result.ai.timing["words"]
    wer = compare([Expected(w["i"], w["text"], w["start_ms"]) for w in words], heard).wer
    row = {"voice": voice, "seconds": round(len(result.ai.audio) / SAMPLE_RATE, 1), "wer": round(wer, 4)}
    if language == "en":  # UTMOS is trained on English speech; its score is not meaningful for Spanish
        row.update(mos_of(audio16, predictor))
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", choices=("en", "es"), default="en")
    parser.add_argument("--voices", default="")
    args = parser.parse_args()
    voices = args.voices.split(",") if args.voices else (ENGLISH_VOICES if args.lang == "en" else SPANISH_VOICES)
    sample = json.loads((PARK if args.lang == "en" else SPANISH).read_text())
    content = first_paragraphs(sample["content"])
    predictor = load_predictor() if args.lang == "en" else None
    rows = []
    for voice in voices:
        row = evaluate(voice, args.lang, content, predictor)
        rows.append(row)
        sys.stdout.write(json.dumps(row) + "\n")
        sys.stdout.flush()
    key = (lambda r: -(r.get("meanMos") or 0)) if args.lang == "en" else (lambda r: r["wer"])
    sys.stdout.write("\nRANKED\n")
    for r in sorted(rows, key=key):
        sys.stdout.write(f"{r['voice']:<12} " + (f"MOS {r.get('meanMos')}  p10 {r.get('p10Mos')}  " if args.lang == "en" else "") + f"WER {r['wer']:.3f}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
