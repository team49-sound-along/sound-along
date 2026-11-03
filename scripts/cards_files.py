"""Copy the reviewed cards documents (samples/cards/*.cards.json) and their place pictures (samples/cards/images/) into data/."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

_IMAGE = re.compile(r"[0-9a-zA-Z-]+\.(?:place|word)-[a-z0-9-]+-[0-9a-f]{8}\.(?:jpg|png)")


def publish_cards(source: Path, data: Path) -> list[str]:
    """Copy every `<id>.cards.json` from `source` into `data`; return the file names copied. A missing folder copies nothing."""
    data.mkdir(parents=True, exist_ok=True)
    copied = []
    images = source / "images"
    wanted = [*sorted(source.glob("*.cards.json")), *(sorted(p for p in images.glob("*.*") if _IMAGE.fullmatch(p.name)) if images.is_dir() else [])]
    for path in wanted:
        shutil.copyfile(path, data / path.name)
        copied.append(path.name)
    return copied
