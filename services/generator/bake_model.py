"""Build-time only: download the pinned Kokoro-82M files into HF_HOME and point refs/main at them.

kokoro loads the repo with the default revision ("main"), so offline lookups need refs/main to exist;
snapshot_download with a commit hash does not write it.
"""
from __future__ import annotations

from pathlib import Path

from huggingface_hub import snapshot_download
from huggingface_hub.constants import HF_HUB_CACHE

REPO = "hexgrad/Kokoro-82M"
REVISION = "f3ff3571791e39611d31c381e3a41a3af07b4987"
FILES = ["config.json", "kokoro-v1_0.pth", "voices/af_heart.pt"]


def main() -> None:
    snapshot_download(REPO, revision=REVISION, allow_patterns=FILES)
    refs = Path(HF_HUB_CACHE) / "models--hexgrad--Kokoro-82M" / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    (refs / "main").write_text(REVISION)


if __name__ == "__main__":
    main()
