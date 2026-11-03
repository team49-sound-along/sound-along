"""Get the local app back to a clean demo state. DRY RUN by default: it only lists what it would change.

  .venv/bin/python scripts/reset_demo.py            # show what would be cleared
  .venv/bin/python scripts/reset_demo.py --apply    # do it (stop or restart the server afterwards: it caches state in memory)

Cleared:  the play / word-tap / completion counters, assignments, blind-test ratings, and every passage a teacher generated
          (its audio, timing, cards and raw input).
          translations of those passages (they have no raw/ file, so they are found by the link in their timing file).
Kept:     the built-in sample passages and their translations, settings, pronunciation fixes, dismissed review items, the listening-test clips.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

ZERO_EVENTS = {"plays": 0, "wordTaps": 0, "completions": 0}
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SAMPLES = Path(__file__).resolve().parent.parent / "samples"
GENERATED_SUFFIXES = (".mp3", ".timing.json", ".soundalong.json", ".cards.json")


def generated_ids(data: Path, samples: Path = SAMPLES) -> list[str]:
    """Ids of passages a teacher generated. Three checks must all pass, so a sample can never be listed: the raw input says
    source "generated", the name is a UUID, and no file in samples/ has that id."""
    built_in = {p.stem for p in samples.glob("*.json")} if samples.is_dir() else set()
    ids = []
    for raw in sorted((data / "raw").glob("*.json")) if (data / "raw").is_dir() else []:
        try:
            content = json.loads(raw.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(content, dict) and content.get("source") == "generated" and UUID.match(raw.stem) and raw.stem not in built_in:
            ids.append(raw.stem)
    return ids


def pair_id(timing_file: Path) -> str | None:
    """The linked variant's id from a timing document, or None."""
    try:
        value = json.loads(timing_file.read_text(encoding="utf-8")).get("pairId")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    return value if isinstance(value, str) else None


def _translation_source(timing_file: Path) -> str | None:
    """The source passage id of a translation (timing.translationOf.id), or None."""
    try:
        link = json.loads(timing_file.read_text(encoding="utf-8")).get("translationOf")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    return link.get("id") if isinstance(link, dict) and isinstance(link.get("id"), str) else None


def plan(data: Path, samples: Path = SAMPLES) -> dict:
    """What a reset would do, computed without touching anything."""
    state_file = data / "state.json"
    try:
        state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    except (OSError, json.JSONDecodeError) as err:
        raise SystemExit(f"Cannot read {state_file}: {err}. Nothing was changed.") from err
    ids = generated_ids(data, samples)
    built_in = {p.stem for p in samples.glob("*.json")} if samples.is_dir() else set()
    wanted = list(ids)
    for i in ids:  # a teacher's recording makes a linked human variant with its own files
        pair = pair_id(data / f"{i}.timing.json")
        if pair and UUID.match(pair) and pair not in built_in and pair not in wanted:
            wanted.append(pair)
    doomed = set(wanted)
    for timing in sorted(data.glob("*.timing.json")):  # translations have no raw/ file: remove those whose source is deleted or missing
        tid = timing.name.removesuffix(".timing.json")
        if tid in doomed or not UUID.match(tid) or tid in built_in:
            continue
        link = _translation_source(timing)
        if link and (link in doomed or (link not in built_in and not (data / f"{link}.timing.json").exists())):
            wanted.append(tid)
            doomed.add(tid)
    files = [p for i in wanted for p in [data / "raw" / f"{i}.json", *(data / f"{i}{s}" for s in GENERATED_SUFFIXES),
                                         *sorted(data.glob(f"{i}.place-*")), *sorted(data.glob(f"{i}.word-*"))] if p.exists()]
    return {
        "events": state.get("events", ZERO_EVENTS),
        "assignments": len(state.get("assignments", [])),
        "ratings": len(state.get("ratings", [])),
        "passages": ids,
        "files": files,
        "state": state,
    }


def apply(data: Path, current: dict) -> None:
    """Write the cleaned state and delete the generated passages' files. Settings and everything else in state.json are kept."""
    cleaned = {**current["state"], "events": dict(ZERO_EVENTS), "assignments": []}
    cleaned.pop("ratings", None)
    target = data / "state.json"
    temp = target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(cleaned, indent=1), encoding="utf-8")
    os.replace(temp, target)  # atomic: a reader never sees half a file
    for path in current["files"]:
        path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    parser.add_argument("--apply", action="store_true", help="actually clear (default: dry run)")
    args = parser.parse_args()
    current = plan(args.data)
    print(f"events: {current['events']}  assignments: {current['assignments']}  ratings: {current['ratings']}")
    print(f"teacher-generated passages: {len(current['passages'])} ({len(current['files'])} files)")
    for path in current["files"]:
        print(f"  would delete {path.relative_to(args.data)}")
    if not args.apply:
        print("\nDry run: nothing changed. Run again with --apply to clear it.")
        return 0
    apply(args.data, current)
    print("\nCleared. Restart the server so it re-reads state.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
