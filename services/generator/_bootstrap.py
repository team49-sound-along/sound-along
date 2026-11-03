"""Make the synth and parse packages importable, in the repo layout and in the container layout."""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CANDIDATE_ROOTS = (_HERE, _HERE.parent)  # container: /var/task/{synth,parse}; repo: services/{synth,parse}


def ensure_paths() -> None:
    for name in ("synth", "parse"):
        for root in _CANDIDATE_ROOTS:
            path = root / name
            if path.is_dir():
                if str(path) not in sys.path:
                    sys.path.insert(0, str(path))
                break


ensure_paths()
