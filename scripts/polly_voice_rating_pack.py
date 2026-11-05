"""A blind rating pack of the candidate Amazon Polly voices AND our existing reference voices, English and Spanish.

Every voice reads the exact same sentences that the reference clips in web/public/voice-samples were made from (scripts/build_voice_samples.py TEXT),
so a Polly voice is compared fairly with Heart, Hadley, Everly, Bryony, Trevor (English) and Dora, Alex (Spanish). The reference clips are the
files that already exist, so no PyTorch is needed to build the pack. Polly voices also read two extra shared sentences (a Spanish name inside an
English sentence, an English word inside a Spanish one) in a separate "mixed" folder, because the references cannot be rebuilt without PyTorch.

Clips get random codes and are shuffled; the answer key is written NEXT TO (never inside) the folder and is git-ignored.

    python3 scripts/polly_voice_rating_pack.py --dry-run                         # which clips, characters, estimated cost; no AWS call
    AWS_PROFILE=<profile> python3 scripts/polly_voice_rating_pack.py             # makes the pack (needs polly:SynthesizeSpeech)
    AWS_PROFILE=<profile> .venv/bin/python scripts/polly_voice_rating_pack.py --score   # also predicts naturalness (UTMOS) for every clip

After listening, put the raters' scores in a ratings.json ({"<code>": [4, 5, 3]}) and run scripts/apply_polly_ratings.py.
Only Polly's SynthesizeSpeech is called. Cost: a few cents (neural $16, generative $30 per million characters).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "synth"))
sys.path.insert(0, str(ROOT / "services" / "eval"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from build_voice_samples import TEXT as SHARED_TEXT  # noqa: E402  (the sentences the reference clips were made from)
from engine import SAMPLE_RATE, SentenceAudio  # noqa: E402
from mixed import ForeignSpan  # noqa: E402
from mp3 import encode_mp3  # noqa: E402
from polly_engine import PollyEngine, _is_invalid_ssml, canonical_voice  # noqa: E402
from polly_rating_pack import USD_PER_MILLION_CHARS  # noqa: E402
from ssml import build_ssml  # noqa: E402

VOICES_FILE = ROOT / "services" / "api" / "config" / "polly-voices.json"
SAMPLES_DIR = ROOT / "web" / "public" / "voice-samples"
LANGUAGES = ("en", "es")
POLLY_ENGINES = ("neural", "generative")
# Existing voices every Polly voice is compared against: (voice id, plain name). Their clips are web/public/voice-samples/<id>.mp3.
REFERENCES: dict[str, tuple[tuple[str, str], ...]] = {
    "en": (("af_heart", "Heart"), ("phonon_hadley", "Hadley"), ("phonon_everly", "Everly"), ("phonon_bryony", "Bryony"), ("phonon_trevor", "Trevor")),
    "es": (("ef_dora", "Dora"), ("em_alex", "Alex")),
}
# One sentence per language with a word of the other language inside it: (sentence, the foreign word, its language).
MIXED = {
    "en": ("My friend Marisol lives near the river.", "Marisol", "es"),
    "es": ("Mi hermano juega al soccer los sábados.", "soccer", "en"),
}
CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ23456789"
SHEET = """# Voice rating ({language}, about {n} clips, 15 minutes)

Every clip reads the same short text. You are not told which voice is which. Listen with headphones, in any order.

## For each clip answer these 5 questions
1. **Human or computer?**  Human / Computer / Not sure
2. **How natural does it sound?**  1 = robotic, 5 = like a real person  (this is the score that counts)
3. **Any glitch?** (pops, clicks, cut-off words, strange sounds)  No / Yes: where
4. **Is any word pronounced wrongly or oddly?**  No / Yes: which word
5. **Would you be happy for a child to learn to read with this voice?**  Yes / Maybe / No

The clips in the "mixed" folder have a word of the other language inside the sentence: also say whether that word sounds right.
At the end: **favorite** and **least favorite** clip, and any comment. Please use at least 3 people{native}.
"""


@dataclass(frozen=True)
class Entry:
    kind: str  # "reference" | "polly"
    voice: str
    engine: str  # "polly engine" for Polly voices, "kokoro" or "phonon" for references
    language: str
    group: str  # "same" (the reference sentences) | "mixed"
    accent: str = ""


@dataclass(frozen=True)
class Clip:
    code: str
    entry: Entry
    score: float | None = None


class _AudioOnly(PollyEngine):
    """Polly audio without the speech-mark request: one request per sentence. A sentence with a foreign span uses SSML <lang> and falls back to plain text."""

    def synthesize(self, sentence: str, spans: Sequence[ForeignSpan] = ()) -> SentenceAudio:
        if spans:
            doc = build_ssml(sentence, spans)
            try:
                return SentenceAudio(self._audio(doc.ssml, doc), (), len(spans))
            except Exception as exc:  # noqa: BLE001
                if not _is_invalid_ssml(exc):
                    raise
        return SentenceAudio(self._audio(sentence), ())


def polly_candidates(voices_file: Path = VOICES_FILE) -> list[dict[str, Any]]:
    return [v for v in json.loads(voices_file.read_text()) if v.get("engine") == "polly"]


def plan(language: str, voices_file: Path = VOICES_FILE) -> list[Entry]:
    """Every clip for one language: the existing reference voices and every (Polly voice, neural|generative) pair, on the shared sentences,
    plus every Polly pair on the mixed-language sentence. Standard voices are left out: they are the old robotic ones."""
    entries = [Entry("reference", vid, "kokoro" if vid.startswith(("af_", "ef_", "em_")) else "phonon", language, "same") for vid, _ in REFERENCES[language]]
    polly = [
        Entry("polly", canonical_voice(v["id"]), engine, language, group, v.get("accent", ""))
        for v in polly_candidates(voices_file)
        if v["lang"] == language
        for engine in POLLY_ENGINES
        if engine in v["engines"]
        for group in ("same", "mixed")
    ]
    return entries + polly


def characters(entry: Entry) -> int:
    return len(" ".join(SHARED_TEXT[entry.language])) if entry.group == "same" else len(MIXED[entry.language][0])


def estimate(entries: Sequence[Entry]) -> float:
    return round(sum(USD_PER_MILLION_CHARS[e.engine] * characters(e) / 1_000_000 for e in entries if e.kind == "polly"), 2)


def make_codes(count: int, seed: int) -> list[str]:
    """`count` unique random 4-character codes (the clip names raters see), reproducible for a seed."""
    rng, codes = random.Random(seed), []
    while len(codes) < count:
        code = "".join(rng.choice(CODE_ALPHABET) for _ in range(4))
        if code not in codes:
            codes.append(code)
    return codes


def _normalize(audio: np.ndarray) -> np.ndarray:
    return audio / max(1e-6, float(np.abs(audio).max())) * 0.89  # the same peak level for every clip


def polly_audio(client: Any, entry: Entry) -> np.ndarray:
    engine = _AudioOnly(client, voice=entry.voice, engine=entry.engine)
    gap = np.zeros(int(0.25 * SAMPLE_RATE), dtype=np.float32)
    if entry.group == "mixed":
        sentence, word, foreign = MIXED[entry.language]
        start = sentence.index(word)
        parts = [engine.synthesize(sentence, [ForeignSpan(start, start + len(word), foreign)]).audio, gap]
    else:
        parts = [part for s in SHARED_TEXT[entry.language] for part in (engine.synthesize(s).audio, gap)]
    return np.concatenate(parts).astype(np.float32)


def reference_audio(entry: Entry, samples_dir: Path = SAMPLES_DIR) -> np.ndarray | None:
    """The existing clip of a reference voice at the pipeline rate, or None when its file is missing."""
    path = samples_dir / f"{entry.voice}.mp3"
    if not path.exists():
        return None
    from asr_words import decode_audio

    return decode_audio(str(path), SAMPLE_RATE)


Scorer = Callable[[np.ndarray], "float | None"]


def build(client: Any, out_dir: Path, key_file: Path, seed: int = 2026, scorer: Scorer | None = None, samples_dir: Path = SAMPLES_DIR, voices_file: Path = VOICES_FILE) -> tuple[list[Clip], list[str]]:
    """Make the pack. Returns (clips, names of reference voices whose clip file is missing). The same clips are written to `key_file` (outside `out_dir`)."""
    entries = [e for lang in LANGUAGES for e in plan(lang, voices_file)]
    random.Random(seed).shuffle(entries)
    codes = make_codes(len(entries), seed)
    clips: list[Clip] = []
    missing: list[str] = []
    for entry, code in zip(entries, codes):
        audio = reference_audio(entry, samples_dir) if entry.kind == "reference" else polly_audio(client, entry)
        if audio is None or audio.size == 0:
            missing.append(entry.voice)
            continue
        audio = _normalize(audio)
        folder = out_dir / entry.language / ("clips" if entry.group == "same" else "mixed")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{code}.mp3").write_bytes(encode_mp3(audio, SAMPLE_RATE, 96))  # one codec and bitrate for every clip, so it cannot give anything away
        score = scorer(audio) if scorer else None
        clips.append(Clip(code, entry, None if score is None else round(float(score), 3)))
    _write_sheets(out_dir, clips)
    write_key(key_file, clips)
    return clips, missing


def _write_sheets(out_dir: Path, clips: Sequence[Clip]) -> None:
    for lang, name, native in (("en", "English", ""), ("es", "Spanish", ", ideally native Spanish speakers")):
        mine = sorted(c.code for c in clips if c.entry.language == lang)
        folder = out_dir / lang
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "READ ME FIRST - rating sheet.md").write_text(SHEET.format(language=name, n=len(mine), native=native))
        (folder / "rating-sheet.csv").write_text("Rater name,Clip,Human/Computer/Not sure,Natural 1-5,Glitch (where),Wrong word,OK for a child (Yes/Maybe/No),Comment\n" + "".join(f",{c},,,,,,\n" for c in mine))


KEY_FIELDS = ("code", "language", "group", "kind", "voice", "engine", "accent")


def write_key(path: Path, clips: Sequence[Clip]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(KEY_FIELDS)
        for c in sorted(clips, key=lambda c: (c.entry.language, c.entry.group, c.code)):
            e = c.entry
            writer.writerow([c.code, e.language, e.group, e.kind, e.voice, e.engine, e.accent])


def read_key(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


# ---- Objective naturalness (UTMOS) -------------------------------------------------------------------------------------------------
SCORE_FIELDS = ("voice", "engine", "language", "group", "kind", "score")


def load_scorer() -> tuple[Scorer | None, str]:
    """(scorer, message). The scorer maps 24 kHz mono audio to a predicted MOS. When UTMOS cannot run here (no torch/torchaudio, or its weights
    cannot be fetched) the scorer is None and the message says why; the pack is still built."""
    try:
        from asr_words import resample_to_16k
        from quality_lab import load_predictor, mos_of

        predictor = load_predictor()
    except Exception as exc:  # noqa: BLE001
        return None, f"UTMOS naturalness scoring is not available here ({type(exc).__name__}: {str(exc)[:100]}). Continuing without scores."

    def score(audio: np.ndarray) -> float | None:
        mos = mos_of(resample_to_16k(audio, SAMPLE_RATE), predictor, window_s=4)
        return mos["meanMos"]

    return score, "UTMOS is on: every clip gets a predicted naturalness score (trained on English speech, so Spanish scores are only indicative)."


def score_rows(clips: Sequence[Clip]) -> list[dict[str, Any]]:
    return [
        {"voice": c.entry.voice, "engine": c.entry.engine, "language": c.entry.language, "group": c.entry.group, "kind": c.entry.kind, "score": c.score}
        for c in clips
        if c.score is not None
    ]


def write_scores_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SCORE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def ranked(rows: Sequence[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    """One language's shared-sentence rows, best score first."""
    mine = [r for r in rows if r["language"] == language and r["group"] == "same" and r["score"] is not None]
    return sorted(mine, key=lambda r: (-r["score"], r["voice"], r["engine"]))


def summary_lines(rows: Sequence[dict[str, Any]]) -> list[str]:
    """A ranked table per language with the references marked (*), then plain statements: which Polly voices score above or below the best reference."""
    lines: list[str] = []
    for language in LANGUAGES:
        table = ranked(rows, language)
        if not table:
            continue
        lines.append(f"\n{'English' if language == 'en' else 'Spanish'} (predicted naturalness, higher is better; * = existing reference voice)")
        lines += [f"{n:>2}. {r['score']:.2f}  {'*' if r['kind'] == 'reference' else ' '} {r['voice']} ({r['engine']})" for n, r in enumerate(table, 1)]
        refs = [r for r in table if r["kind"] == "reference"]
        if refs:
            best = refs[0]
            above = sorted({r["voice"] for r in table if r["kind"] == "polly" and r["score"] > best["score"]})
            below = sorted({r["voice"] for r in table if r["kind"] == "polly" and r["score"] <= best["score"]} - set(above))
            lines.append(f"Best reference: {best['voice']} ({best['score']:.2f}). Polly voices above it: {', '.join(above) or 'none'}. At or below it: {', '.join(below) or 'none'}.")
        if language == "es":
            lines.append("Note: this predictor is trained on English speech; treat Spanish scores as indicative and rely on the listening test.")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=Path.home() / "Downloads" / "Polly voice rating")
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and the estimated cost; call nothing")
    parser.add_argument("--score", action="store_true", help="also predict naturalness (UTMOS) for every clip and write polly-voice-scores.csv next to the folder")
    args = parser.parse_args(argv)
    entries = [e for lang in LANGUAGES for e in plan(lang)]
    polly = [e for e in entries if e.kind == "polly"]
    print(f"{len(entries)} clips: {len(entries) - len(polly)} existing reference voices and {len(polly)} Amazon Polly clips; estimated Polly cost about ${estimate(entries)} in region {args.region}")
    if args.dry_run:
        return 0
    scorer = None
    if args.score:
        scorer, message = load_scorer()
        print(message)
    import boto3

    client = boto3.client("polly", region_name=args.region)
    key_file = args.out.parent / f"{args.out.name} KEY (do not share).csv"
    clips, missing = build(client, args.out, key_file, scorer=scorer)
    print(f"wrote {len(clips)} clips to {args.out}; the answer key is {key_file}")
    if missing:
        print("No clip made for: " + ", ".join(sorted(set(missing))) + " (a reference file is missing; run scripts/build_voice_samples.py for it)")
    rows = score_rows(clips)
    if rows:
        scores_file = args.out.parent / f"{args.out.name} scores (do not share).csv"
        write_scores_csv(scores_file, rows)
        print("\n".join(summary_lines(rows)) + f"\n\nScores written to {scores_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
