"""A blind rating pack of Amazon Polly's Spanish voices: every voice and engine reads the same passage, clips are shuffled and numbered, and the answer key
is written next to (not inside) the folder you send to raters.

    python3 scripts/polly_rating_pack.py --dry-run                       # which voices, how many characters, estimated cost; no AWS call
    AWS_PROFILE=<sandbox profile> python3 scripts/polly_rating_pack.py   # makes the clips (needs credentials that may call polly:SynthesizeSpeech)

Run it once the sandbox credentials are connected. The cost is a few cents to about $1 (neural $16, generative $30, long-form $100 per million characters).
Nothing is deployed and nothing but Polly's SynthesizeSpeech is called.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "synth"))

import numpy as np  # noqa: E402

from engine import SAMPLE_RATE, SentenceAudio  # noqa: E402
from mp3 import encode_mp3  # noqa: E402
from polly_engine import POLLY_VOICES, PollyEngine  # noqa: E402

USD_PER_MILLION_CHARS = {"neural": 16, "generative": 30, "long-form": 100, "standard": 4}
SAMPLE = ROOT / "samples" / "5e5f1d3c-7a2b-4c9e-8d1a-3b6f2c9e4a70.json"  # "Un día en el parque", a short original Spanish passage
SHEET = """# Spanish voice rating (about {n} clips, 15 minutes)

Every clip reads the same short Spanish passage. You are not told which voice is which. Listen with headphones, in any order.

## For each clip answer these 5 questions
1. **Human or computer?**  Human / Computer / Not sure
2. **How natural does it sound?**  1 = robotic, 5 = like a real person
3. **Any glitch?** (pops, clicks, cut-off words, strange sounds)  No / Yes: where
4. **Is any word pronounced wrongly or oddly?**  No / Yes: which word
5. **Would you be happy for a child to learn to read with this voice?**  Yes / Maybe / No

At the end: **favorite** and **least favorite** clip, and any comment. Please use at least 3 people, ideally native Spanish speakers.
"""


class _AudioOnly(PollyEngine):
    """Polly audio without the speech-mark request, so a sample costs one request per sentence."""

    def synthesize(self, sentence: str) -> SentenceAudio:
        return SentenceAudio(self._audio(sentence), ())


def plan(language_prefix: str = "es") -> list[tuple[str, str]]:
    """Every (voice, engine) pair Polly offers for the language, in a stable order. Standard voices are left out: they are the old robotic ones."""
    return [(voice, engine) for voice, info in POLLY_VOICES.items() if info["lang"].startswith(language_prefix) for engine in info["engines"]]


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def estimate_usd(pairs: list[tuple[str, str]], chars: int) -> float:
    return round(sum(USD_PER_MILLION_CHARS[engine] * chars / 1_000_000 for _, engine in pairs), 2)


def passage_text(path: Path = SAMPLE, max_chars: int = 1500) -> str:
    plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", json.loads(path.read_text())["content"])).strip()
    out = ""
    for s in sentences(plain):
        if len(out) + len(s) > max_chars:
            break
        out += s + " "
    return out.strip()


def build(client: Any, text: str, out_dir: Path, key_file: Path, seed: int = 2026) -> list[tuple[str, str, str]]:
    """Make the clips. Returns [(clip name, voice, engine)]; the same list is written to `key_file`."""
    pairs = plan()
    random.Random(seed).shuffle(pairs)
    (out_dir / "clips").mkdir(parents=True, exist_ok=True)
    gap = np.zeros(int(0.25 * SAMPLE_RATE), dtype=np.float32)
    key = []
    for n, (voice, engine) in enumerate(pairs, 1):
        engine_obj = _AudioOnly(client, voice=voice, engine=engine)
        parts = []
        for sentence in sentences(text):
            parts += [engine_obj.synthesize(sentence).audio, gap]
        audio = np.concatenate(parts).astype(np.float32)
        audio = audio / max(1e-6, float(np.abs(audio).max())) * 0.89  # the same peak level for every clip
        (out_dir / "clips" / f"Voice-{n}.mp3").write_bytes(encode_mp3(audio, SAMPLE_RATE, 96))
        key.append((f"Voice-{n}", voice, engine))
    (out_dir / "READ ME FIRST - rating sheet.md").write_text(SHEET.format(n=len(key)))
    (out_dir / "rating-sheet.csv").write_text("Rater name,Clip,Human/Computer/Not sure,Natural 1-5,Glitch (where),Wrong word,OK for a child (Yes/Maybe/No),Comment\n" + "".join(f",{c},,,,,,\n" for c, _, _ in key))
    key_file.write_text("ANSWER KEY - keep this away from the raters\n\n" + "\n".join(f"{c}: Amazon Polly {v} ({e} engine)" for c, v, e in key) + "\n")
    return key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=Path.home() / "Downloads" / "Spanish Polly voice rating")
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and the estimated cost; call nothing")
    args = parser.parse_args(argv)
    text, pairs = passage_text(), plan()
    cost = estimate_usd(pairs, len(text))
    print(f"{len(pairs)} clips ({', '.join(f'{v}/{e}' for v, e in pairs)})\n{len(text)} characters each; estimated cost about ${cost} in region {args.region}")
    if args.dry_run:
        return 0
    import boto3

    client = boto3.client("polly", region_name=args.region)
    key = build(client, text, args.out, args.out.parent / f"{args.out.name} KEY (do not share).txt")
    print(f"wrote {len(key)} clips to {args.out}; the answer key is next to the folder")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
