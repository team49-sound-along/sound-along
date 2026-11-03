"""Make the other-language version of every demo text (English -> Spanish, Spanish -> English) and link it to the original.

  .venv/bin/python scripts/build_translations.py

Each translation is its own passage (its own audio, word timing, phrase breaks and cards) linked both ways with a sentence map. Run it after
scripts/build_samples.py. Uploaded passages get the same treatment automatically when they are published (services/synth/translate_flow.py).
Machine translation: the product labels it, and a Spanish speaker should review it.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "services" / "synth"), str(ROOT / "services" / "parse")]
from translate_flow import other_language, publish_translation  # noqa: E402

DATA = ROOT / "data"
SAMPLES = ROOT / "samples"
SETTINGS = {"voice": "af_heart", "voiceEs": "ef_dora", "speed": 0.95, "mp3Kbps": 48}


def main() -> int:
    failures = 0
    for path in sorted(SAMPLES.glob("*.json")):
        sample = json.loads(path.read_text(encoding="utf-8"))
        timing_path = DATA / f"{path.stem}.timing.json"
        if not timing_path.exists():
            print(f"{path.stem[:8]}: not built yet (run build_samples.py first), skipped")
            continue
        language = sample.get("language", "en")
        passage = {"uuid": path.stem, "title": sample["title"], "content": sample["content"], "language": language, "source": "sample",
                   "settings": SETTINGS, "pronunciations": {}}
        pair = json.loads(timing_path.read_text(encoding="utf-8")).get("pairId")
        started = time.time()
        tid = publish_translation(passage, DATA, other_language(language), source_ids=[path.stem, *([pair] if pair else [])], safe=True)
        if tid:
            print(f"{path.stem[:8]} ({language}) -> {other_language(language)} {tid[:8]} in {time.time() - started:.0f}s")
        else:
            failures += 1
            print(f"{path.stem[:8]}: translation FAILED (see the message above)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
