"""Copy the reviewed cards documents (samples/cards/*.cards.json) next to the audio and timing files in data/."""
from __future__ import annotations

import shutil
from pathlib import Path


def publish_cards(source: Path, data: Path) -> list[str]:
    """Copy every `<id>.cards.json` from `source` into `data`; return the file names copied. A missing folder copies nothing."""
    data.mkdir(parents=True, exist_ok=True)
    copied = []
    for path in sorted(source.glob("*.cards.json")):
        shutil.copyfile(path, data / path.name)
        copied.append(path.name)
    return copied
