"""Turn the human listening results into services/api/config/polly-voice-ratings.json, which decides which Polly voices Settings lists as recommended.

    python3 scripts/apply_polly_ratings.py --ratings ratings.json --key "Polly voice rating KEY (do not share).csv" [--margin 0.2]

ratings.json maps a clip code (the same codes for reference voices and Polly candidates) to the naturalness scores (1-5) the raters gave it:
    {"K7QD": [4, 5, 3], "B2MX": 4.5, "ZC4F": {"scores": [3, 4]}}
The key is the CSV written next to the pack by scripts/polly_voice_rating_pack.py. Only the shared-sentence clips count; "mixed" clips are for checking.

RULE (also in services/api/config/VOICES.md): a Polly voice is recommended only when one of its engines (neural or generative) scores at or above the
BEST existing reference voice of its language (Heart, Hadley, Everly, Bryony, Trevor for English; Dora, Alex for Spanish), or within --margin of it
(default 0.2 points on the 1-5 scale). With no rated reference for a language, nothing in that language is recommended.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from polly_voice_rating_pack import read_key  # noqa: E402

DEFAULT_MARGIN = 0.2
OUT = ROOT / "services" / "api" / "config" / "polly-voice-ratings.json"
RULE = ("A Polly voice is recommended only when its human listening score (neural or generative) is at or above the best existing reference voice of its "
        "language, or within the margin. Written by scripts/apply_polly_ratings.py from the blind listening test.")


def scores_of(value: Any) -> list[float]:
    """The numeric scores in one ratings.json entry (a number, a list, or {"scores": [...]}). Anything else is an error."""
    raw = value.get("scores") if isinstance(value, Mapping) else value
    items = raw if isinstance(raw, list) else [raw]
    if not items or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in items):
        raise ValueError(f"Not a score or a list of scores: {value!r}")
    if any(not 1 <= x <= 5 for x in items):
        raise ValueError(f"Scores must be from 1 to 5: {value!r}")
    return [float(x) for x in items]


def clip_means(ratings: Mapping[str, Any], key: Sequence[Mapping[str, str]]) -> dict[str, float]:
    """Mean score per code. A code that is not in the key is an error (a typo would silently drop a rating)."""
    known = {row["code"] for row in key}
    unknown = sorted(set(ratings) - known)
    if unknown:
        raise ValueError("These codes are not in the key: " + ", ".join(unknown))
    return {code: round(statistics.fmean(scores_of(v)), 3) for code, v in ratings.items()}


def apply(ratings: Mapping[str, Any], key: Sequence[Mapping[str, str]], margin: float = DEFAULT_MARGIN) -> dict[str, Any]:
    """The contents of polly-voice-ratings.json for these listening results."""
    means = clip_means(ratings, key)
    rated = [(row, means[row["code"]]) for row in key if row["code"] in means and row["group"] == "same"]
    references: dict[str, dict[str, Any]] = {}
    polly: dict[str, dict[str, Any]] = {}
    for row, score in rated:
        if row["kind"] == "reference":
            ref = references.setdefault(row["language"], {"scores": {}})
            ref["scores"][row["voice"]] = score
        else:
            polly.setdefault(row["voice"], {"language": row["language"], "engines": {}})["engines"][row["engine"]] = score
    for ref in references.values():
        best = max(ref["scores"], key=ref["scores"].get)
        ref.update(best=best, bestScore=ref["scores"][best])
    recommended = []
    for voice, info in polly.items():
        info["qualifyingEngines"] = []
        ref = references.get(info["language"])
        if ref:
            info["qualifyingEngines"] = sorted(e for e, s in info["engines"].items() if s >= ref["bestScore"] - margin)
            info["atOrAboveBestReference"] = any(s >= ref["bestScore"] for s in info["engines"].values())
        if info["qualifyingEngines"]:
            recommended.append(voice)
    return {"version": 1, "rule": RULE, "margin": margin, "references": references, "ratings": polly, "recommended": sorted(recommended)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ratings", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--margin", type=float, default=DEFAULT_MARGIN)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    try:
        result = apply(json.loads(args.ratings.read_text()), read_key(args.key), args.margin)
    except (ValueError, OSError) as err:
        print(f"Could not apply the ratings: {err}", file=sys.stderr)
        return 1
    args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    for lang, ref in result["references"].items():
        print(f"{lang}: best reference {ref['best']} ({ref['bestScore']})")
    print(f"Recommended Polly voices: {', '.join(result['recommended']) or 'none'}\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
