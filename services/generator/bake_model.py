"""Build-time only: download the pinned models into HF_HOME and point refs/main at them.

 * Kokoro-82M weights plus every US/UK English voice (teachers choose the voice in Settings, so all must be present).
 * faster-whisper small.en (MIT) for aligning uploaded recordings and the pronunciation check.

The libraries load repos with the default revision ("main"), so offline lookups need refs/main to exist;
snapshot_download with a commit hash does not write it.
"""
from __future__ import annotations

from pathlib import Path

from huggingface_hub import snapshot_download
from huggingface_hub.constants import HF_HUB_CACHE

MODELS = (
    (
        "hexgrad/Kokoro-82M",
        "f3ff3571791e39611d31c381e3a41a3af07b4987",
        ["config.json", "kokoro-v1_0.pth", "voices/af_*.pt", "voices/am_*.pt", "voices/bf_*.pt", "voices/bm_*.pt"],
    ),
    (
        "Systran/faster-whisper-small.en",
        "d1d751a5f8271d482d14ca55d9e2deeebbae577f",
        ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"],
    ),
)


def main() -> None:
    for repo, revision, files in MODELS:
        snapshot_download(repo, revision=revision, allow_patterns=files)
        refs = Path(HF_HUB_CACHE) / f"models--{repo.replace('/', '--')}" / "refs"
        refs.mkdir(parents=True, exist_ok=True)
        (refs / "main").write_text(revision)


if __name__ == "__main__":
    main()
